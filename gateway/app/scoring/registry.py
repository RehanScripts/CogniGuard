"""Model registry (read-side) -- resolves the `production` model_registry row, downloads
the S3 artifact to MODEL_DIR, caches the loaded object + version (Implementation.md
Phase 6). Postgres is touched here ONLY for this startup/reload metadata resolution --
not a per-request feature read, so this does not violate CLAUDE.md's Redis-only
hot-path invariant (that invariant is about scoring-feature lookups, not model-artifact
resolution). `training/registry.py` is the write-side counterpart (offline training).
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass

import joblib
import onnxruntime as ort
from sqlalchemy import select

from ..config import settings
from ..db import SessionLocal
from ..models.governance import ModelRegistry
from ..s3_client import get_s3

# model_name -> (artifact filename, loader). Phase 13 (Implementation.md) adds the
# onnxruntime path for `lstm_autoencoder`; `isolation_forest`/`xgboost_txn` keep their
# existing joblib path unchanged. Anything not listed falls back to the joblib default
# (the pre-Phase-13 behavior for every model_name there was).
_ARTIFACT_SPECS: dict[str, tuple[str, object]] = {
    "isolation_forest": ("model.joblib", joblib.load),
    "xgboost_txn": ("model.joblib", joblib.load),
    "lstm_autoencoder": ("model.onnx", ort.InferenceSession),
}
_DEFAULT_SPEC = ("model.joblib", joblib.load)


@dataclass
class LoadedModel:
    model_name: str
    version: str
    model: object
    artifact_uri: str


def _download(artifact_uri: str, local_path: str) -> None:
    """s3://bucket/key -> local_path, creating parent dirs."""
    _, _, rest = artifact_uri.partition("://")
    bucket, _, key = rest.partition("/")
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    get_s3().download_file(bucket, key, local_path)


class Registry:
    """Process-wide cache keyed by model_name. Thread-safe (single lock; load is rare)."""

    def __init__(self) -> None:
        self._cache: dict[str, LoadedModel] = {}
        self._lock = threading.Lock()

    def get(self, model_name: str) -> LoadedModel:
        with self._lock:
            cached = self._cache.get(model_name)
            if cached is not None:
                return cached
            loaded = self._load(model_name)
            self._cache[model_name] = loaded
            return loaded

    def reload(self, model_name: str) -> None:
        """Clear the cache entry (post-promotion); next get() re-resolves + re-downloads."""
        with self._lock:
            self._cache.pop(model_name, None)

    def get_challenger(self, model_name: str) -> LoadedModel | None:
        """Resolve the `stage="staging"` row for `model_name`, if one exists -- used by
        `app.scoring.shadow` to run a challenger alongside the champion (Implementation.md
        Phase 12). Returns `None` rather than raising when no challenger is registered,
        the common case: shadow.py must be a safe no-op then, not an error path. Not
        cached -- challengers are registered rarely and shadow-scored at most once per
        request, so a process-wide cache isn't worth the staleness risk here."""
        try:
            return self._load(model_name, stage="staging")
        except LookupError:
            return None

    def _load(self, model_name: str, *, stage: str = "production") -> LoadedModel:
        with SessionLocal() as session:
            row = session.scalar(
                select(ModelRegistry)
                .where(ModelRegistry.model_name == model_name, ModelRegistry.stage == stage)
                .order_by(ModelRegistry.deployed_at.desc())
            )
        if row is None:
            raise LookupError(f"no {stage} row for model_name={model_name!r}")
        filename, loader = _ARTIFACT_SPECS.get(model_name, _DEFAULT_SPEC)
        local_path = os.path.join(settings.model_dir, model_name, row.version, filename)
        if not os.path.exists(local_path):
            _download(row.artifact_uri, local_path)
        model = loader(local_path)
        return LoadedModel(
            model_name=model_name, version=row.version, model=model, artifact_uri=row.artifact_uri
        )
