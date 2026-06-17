"""`model_registry` writes for offline training (Implementation.md Phase 5).

Promoting a new model to `production` archives the previous production row for that
`model_name` first, so `Registry.get(model_name)` (Phase 6) always resolves exactly one
production row.
"""

from __future__ import annotations

import uuid

from sqlalchemy import update

from app.db import SessionLocal
from app.models.governance import ModelRegistry


def register_model(
    *,
    model_name: str,
    model_type: str,
    version: str,
    artifact_uri: str,
    metrics: dict,
    stage: str = "production",
) -> None:
    with SessionLocal() as session:
        if stage == "production":
            session.execute(
                update(ModelRegistry)
                .where(ModelRegistry.model_name == model_name, ModelRegistry.stage == "production")
                .values(stage="archived")
            )
        session.add(
            ModelRegistry(
                model_id=uuid.uuid4(),
                model_name=model_name,
                model_type=model_type,
                version=version,
                stage=stage,
                artifact_uri=artifact_uri,
                metrics=metrics,
            )
        )
        session.commit()
