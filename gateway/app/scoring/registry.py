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
from sqlalchemy import select

from ..config import settings
from ..db import SessionLocal
from ..models.governance import ModelRegistry
from ..s3_client import get_s3


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

    def _load(self, model_name: str) -> LoadedModel:
        with SessionLocal() as session:
            row = session.scalar(
                select(ModelRegistry)
                .where(ModelRegistry.model_name == model_name, ModelRegistry.stage == "production")
                .order_by(ModelRegistry.deployed_at.desc())
            )
        if row is None:
            raise LookupError(f"no production row for model_name={model_name!r}")
        local_path = os.path.join(settings.model_dir, model_name, row.version, "model.joblib")
        if not os.path.exists(local_path):
            _download(row.artifact_uri, local_path)
        model = joblib.load(local_path)
        return LoadedModel(
            model_name=model_name, version=row.version, model=model, artifact_uri=row.artifact_uri
        )
