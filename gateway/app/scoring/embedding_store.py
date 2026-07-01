"""AE encoder embedding store (Phase F4).

Runs the encoder half of the LSTM Autoencoder (lstm_encoder.onnx) on a behavioral
sequence to produce a 16-dim embedding, maintains a per-user centroid in Redis via
exponential moving average, and computes cosine similarity as a supplementary identity
signal alongside the robust-z `behavior_match_score` from `identity.py`.

Architecture note: this is a second inference pass beyond the full autoencoder that runs
for reconstruction error, so it only fires when:
  - a web-channel `behavior_sequence` is available (mobile sends ae_recon_error only), and
  - the encoder model is registered in `model_registry` (graceful no-op otherwise).

The cosine similarity is folded into Trust Score as an optional blending term — it
narrows the gap between a stolen-password + perfect behavioral clone (rare) and a genuine
user with slightly variable rhythm. It never replaces the primary `Behavior_Score` AE
signal.
"""

from __future__ import annotations

import json
import logging
import math
from functools import lru_cache
from typing import TYPE_CHECKING

import numpy as np
from redis import Redis

if TYPE_CHECKING:
    from .registry import Registry

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 16
_ALPHA = 0.15  # EMA update weight for centroid (higher = more responsive)
_MIN_SESSIONS = 3  # require this many sessions before centroid is considered warm
_CENTROID_TTL_S = 90 * 24 * 3600  # 90-day TTL — same as risk baseline


def _k_centroid(user_id: str) -> str:
    return f"behavior:{user_id}:embedding"


def _k_sim(user_id: str) -> str:
    return f"behavior:{user_id}:embedding_sim"


def read_cached_sim(user_id: str, *, redis: Redis) -> float | None:
    """Read the last stored cosine similarity from Redis (written by update_and_score).

    Called by feature_reader.read_bundle() to include embedding_sim in FeatureBundle.
    Returns None if no similarity has been computed yet (cold-start).
    """
    raw = redis.get(_k_sim(user_id))
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity in [-1, 1]; returns 0.0 on zero vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return dot / (na * nb)


@lru_cache(maxsize=1)
def _load_encoder_session(artifact_uri: str):
    """Load the lstm_encoder ONNX artifact once per process (cached)."""
    import onnxruntime as ort

    if artifact_uri.startswith("s3://") or artifact_uri.startswith("models/"):
        from ..s3_client import get_s3
        from ..config import settings

        s3_key = (
            artifact_uri.lstrip("s3://").split("/", 1)[-1]
            if artifact_uri.startswith("s3://")
            else artifact_uri
        )
        try:
            obj = get_s3().get_object(Bucket=settings.s3_bucket, Key=s3_key)
            onnx_bytes = obj["Body"].read()
        except Exception as exc:
            logger.warning("embedding_store: failed to load encoder from S3: %s", exc)
            return None
    else:
        # Local file path
        try:
            with open(artifact_uri, "rb") as f:
                onnx_bytes = f.read()
        except Exception as exc:
            logger.warning("embedding_store: failed to load encoder from %s: %s", artifact_uri, exc)
            return None

    try:
        return ort.InferenceSession(onnx_bytes, providers=["CPUExecutionProvider"])
    except Exception as exc:
        logger.warning("embedding_store: ONNX session creation failed: %s", exc)
        return None


def encode(
    behavior_sequence: list[list[float]],
    registry: "Registry",
) -> list[float] | None:
    """Run the encoder on a `(SEQ_LEN, N_FEATURES)` behavioral sequence.

    Returns the 16-dim embedding, or None if the encoder is unavailable.
    """
    try:
        model_row = registry.get("lstm_encoder")
    except LookupError:
        return None  # encoder not yet trained/registered — silent no-op

    session = _load_encoder_session(model_row.artifact_uri)
    if session is None:
        return None

    try:
        inp = np.array([behavior_sequence], dtype=np.float32)  # (1, SEQ_LEN, N_FEATURES)
        out = session.run(None, {session.get_inputs()[0].name: inp})[0]  # (1, 16)
        return out[0].tolist()
    except Exception as exc:
        logger.warning("embedding_store: encoder inference failed: %s", exc)
        return None


def update_and_score(
    user_id: str,
    embedding: list[float],
    *,
    redis: Redis,
) -> float | None:
    """Update the per-user centroid EMA and return cosine similarity [0, 1].

    Returns None while the centroid is still warming up (< _MIN_SESSIONS sessions).
    """
    key = _k_centroid(user_id)
    raw = redis.get(key)

    centroid: list[float]
    session_count: int

    if raw:
        try:
            data = json.loads(raw)
            centroid = data["centroid"]
            session_count = int(data.get("count", 0))
        except (TypeError, ValueError, KeyError):
            centroid = embedding[:]
            session_count = 1
    else:
        centroid = embedding[:]
        session_count = 1

    # EMA update: new_centroid = alpha * live + (1 - alpha) * old
    if session_count > 1:
        centroid = [_ALPHA * e + (1.0 - _ALPHA) * c for e, c in zip(embedding, centroid)]
    session_count += 1

    redis.set(
        key,
        json.dumps({"centroid": centroid, "count": session_count}),
        ex=_CENTROID_TTL_S,
    )

    if session_count < _MIN_SESSIONS:
        redis.set(_k_sim(user_id), "", ex=_CENTROID_TTL_S)  # mark as computing
        return None  # centroid still cold

    sim = _cosine(embedding, centroid)
    # Map [-1,1] cosine similarity to [0,1] match score
    score = max(0.0, (sim + 1.0) / 2.0)

    # Persist for next request's hot-path read via feature_reader.read_bundle().
    redis.set(_k_sim(user_id), str(score), ex=_CENTROID_TTL_S)
    return score


def embedding_match_score(
    user_id: str,
    behavior_sequence: list[list[float]],
    *,
    registry: "Registry",
    redis: Redis,
) -> float | None:
    """Full pipeline: encode → update centroid → cosine similarity → [0, 1] match score.

    Returns None on cold-start (centroid not warm) or if encoder unavailable.
    Intended to be called off the hot path (BackgroundTask) and cached in Redis;
    the result then read at inference time alongside `Behavior_Score`.
    """
    embedding = encode(behavior_sequence, registry)
    if embedding is None:
        return None
    return update_and_score(user_id, embedding, redis=redis)
