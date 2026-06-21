"""Resolves the current production `lstm_autoencoder_tflite` distribution + per-user
AE calibration for the native Android app (Implementation.md Phase 18). The on-device
AE itself only needs the raw reconstruction error path -- calibration always happens
server-side, same as web (CLAUDE.md: inference reads Redis only) -- but the app
bootstraps both at startup/login so it can pin `ae_model_version` to a real registered
version and render a local risk-preview before the authoritative server round-trip.
"""

from __future__ import annotations

from dataclasses import dataclass

from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..models.governance import ModelRegistry
from ..s3_client import get_s3
from ..scoring import calibration
from ..scoring.calibration import CalibrationParams

MODEL_NAME = "lstm_autoencoder_tflite"
PRESIGNED_URL_TTL_S = 300


@dataclass
class ModelDistribution:
    version: str
    download_url: str
    expires_in_s: int


def _split_s3_uri(artifact_uri: str) -> tuple[str, str]:
    _, _, rest = artifact_uri.partition("://")
    bucket, _, key = rest.partition("/")
    return bucket, key


def resolve_model(db: DbSession) -> ModelDistribution:
    """The `production` row, deployed-at descending (same resolution order as
    `app.scoring.registry.Registry._load`) -- a presigned GET URL rather than proxying
    the binary through the gateway, since the artifact already lives in MinIO/S3."""
    row = db.scalar(
        select(ModelRegistry)
        .where(ModelRegistry.model_name == MODEL_NAME, ModelRegistry.stage == "production")
        .order_by(ModelRegistry.deployed_at.desc())
    )
    if row is None or not row.artifact_uri:
        raise LookupError(f"no production {MODEL_NAME} row")
    bucket, key = _split_s3_uri(row.artifact_uri)
    url = get_s3().generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=PRESIGNED_URL_TTL_S
    )
    return ModelDistribution(
        version=row.version, download_url=url, expires_in_s=PRESIGNED_URL_TTL_S
    )


def resolve_calibration(user_id: str, *, redis: Redis) -> CalibrationParams:
    """Per-user else population else default -- delegates entirely to Phase 13's
    `calibration.load_calibration`, the same lookup the gateway's own scoring path
    uses, so the app's local preview and the server's authoritative score are
    calibrated identically."""
    return calibration.load_calibration(user_id, redis=redis)
