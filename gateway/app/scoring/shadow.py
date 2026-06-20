"""Challenger / shadow scoring (Implementation.md Phase 12): when a `staging` row exists
for `isolation_forest` and/or `xgboost_txn`, run the champion scoring path a second time
with the challenger substituted in, *without acting on it* -- persists one flagged
`RiskScore` row (`is_shadow=True`) for offline champion-vs-challenger comparison
(fraud-value-caught at the bounded FP/step-up budget), never a `Decision` row, never
broadcast to the live SOC feed (`event_producer.emit_risk_score`/`emit_decision`) or
`case_mgmt`. Called from the flow modules (`auth_flow`/`payment_flow`/`behavior_flow`) as
a second `BackgroundTasks.add_task`, alongside the existing `audit.persist_scoring_outcome`
-- same "off the hot path" mechanism, so a challenger run never adds to login/payment
latency.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Mapping

from redis import Redis
from sqlalchemy.orm import Session as DbSession

from ..schemas.features import FeatureBundle
from ..services import audit
from . import stack
from .amplifiers import TxnContext
from .registry import LoadedModel, Registry

logger = logging.getLogger("cogniguard.shadow")

_MODEL_NAMES = ("isolation_forest", "xgboost_txn")


class _ShadowRegistry:
    """Duck-types `Registry.get()`: returns the challenger for any model_name that has
    one, delegates everything else to the real (production-resolving) registry."""

    def __init__(self, registry: Registry, challengers: Mapping[str, LoadedModel]):
        self._registry = registry
        self._challengers = challengers

    def get(self, model_name: str) -> LoadedModel:
        challenger = self._challengers.get(model_name)
        return challenger if challenger is not None else self._registry.get(model_name)


def run_and_persist(
    db: DbSession,
    bundle: FeatureBundle,
    *,
    policy: Mapping[str, Any],
    registry: Registry,
    redis: Redis | None = None,
    txn_context: TxnContext | None = None,
    entity_type: str,
    entity_id: uuid.UUID | str,
    user_id: uuid.UUID | str | None,
) -> None:
    """No-op when no challenger is registered (the common case) -- never raises, this
    runs as a background task and must never affect the request it rides along with."""
    try:
        challengers = {
            name: loaded
            for name in _MODEL_NAMES
            if (loaded := registry.get_challenger(name)) is not None
        }
        if not challengers:
            return

        shadow_registry = _ShadowRegistry(registry, challengers)
        result = stack.score(
            bundle, policy=policy, registry=shadow_registry, txn_context=txn_context, redis=redis
        )
        audit.persist_risk_score(
            db,
            result,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            is_shadow=True,
        )
    except Exception:  # noqa: BLE001 -- background task, must never raise
        logger.exception(
            "shadow scoring failed for entity_type=%s entity_id=%s", entity_type, entity_id
        )
