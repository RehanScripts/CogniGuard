"""Model promotion / rollback (Implementation.md Phase 12): flips `model_registry.stage`
for an existing row -- no re-training, no artifact movement, just the DB-side governance
state change `gateway/app/scoring/registry.py:Registry.get()` reads at inference. Every
flip writes one `audit_logs` row, per CLAUDE.md invariant 7 ("every decision persists
immutably with reason codes") extended here to model-governance decisions.

`training/registry.py:register_model()` is the *write-new-row* path (training scripts);
this module only ever flips `stage` on rows that already exist.
"""

from __future__ import annotations

import argparse

from sqlalchemy import select, update

from app.db import SessionLocal
from app.models.governance import AuditLog, ModelRegistry


def _latest(session, *, model_name: str, stage: str) -> ModelRegistry | None:
    return session.scalar(
        select(ModelRegistry)
        .where(ModelRegistry.model_name == model_name, ModelRegistry.stage == stage)
        .order_by(ModelRegistry.deployed_at.desc())
    )


def promote_to_production(model_name: str, version: str | None = None) -> ModelRegistry:
    """Promote a `staging` challenger to `production`; archive the current production
    row for `model_name` first (so `Registry.get()` still resolves exactly one row).
    `version` defaults to the most recently registered staging row -- the acceptance
    check's `--model xgboost_txn --to production` passes no `--version` at all."""
    with SessionLocal() as session:
        target = (
            session.scalar(
                select(ModelRegistry).where(
                    ModelRegistry.model_name == model_name,
                    ModelRegistry.version == version,
                )
            )
            if version
            else _latest(session, model_name=model_name, stage="staging")
        )
        if target is None:
            raise LookupError(
                f"no staging row found for model_name={model_name!r}"
                + (f" version={version!r}" if version else "")
            )
        if target.stage != "staging":
            raise ValueError(
                f"model {model_name!r} version {target.version!r} is stage={target.stage!r}, "
                "not staging -- only a staging challenger can be promoted"
            )

        previous = _latest(session, model_name=model_name, stage="production")
        if previous is not None:
            session.execute(
                update(ModelRegistry)
                .where(ModelRegistry.model_id == previous.model_id)
                .values(stage="archived")
            )
        target.stage = "production"
        session.add(
            AuditLog(
                actor_type="system",
                actor_id="training.promote",
                action="MODEL_PROMOTED",
                entity_type="model",
                entity_id=target.model_id,
                metadata_={
                    "model_name": model_name,
                    "version": target.version,
                    "previous_version": previous.version if previous else None,
                },
            )
        )
        session.commit()
        session.refresh(target)
        return target


def rollback(model_name: str, version: str) -> ModelRegistry:
    """Flip an `archived` version back to `production` without redeploying artifacts --
    the safety-net path when a promoted challenger turns out to regress."""
    with SessionLocal() as session:
        target = session.scalar(
            select(ModelRegistry).where(
                ModelRegistry.model_name == model_name, ModelRegistry.version == version
            )
        )
        if target is None:
            raise LookupError(f"no row for model_name={model_name!r} version={version!r}")
        if target.stage != "archived":
            raise ValueError(
                f"model {model_name!r} version {version!r} is stage={target.stage!r}, "
                "not archived -- rollback targets a previously-archived version"
            )

        previous = _latest(session, model_name=model_name, stage="production")
        if previous is not None:
            session.execute(
                update(ModelRegistry)
                .where(ModelRegistry.model_id == previous.model_id)
                .values(stage="archived")
            )
        target.stage = "production"
        session.add(
            AuditLog(
                actor_type="system",
                actor_id="training.promote",
                action="MODEL_ROLLBACK",
                entity_type="model",
                entity_id=target.model_id,
                metadata_={
                    "model_name": model_name,
                    "version": target.version,
                    "previous_version": previous.version if previous else None,
                },
            )
        )
        session.commit()
        session.refresh(target)
        return target


def _main() -> None:
    parser = argparse.ArgumentParser(description="Promote/rollback a model_registry row.")
    parser.add_argument("--model", required=True, dest="model_name")
    parser.add_argument("--version", default=None)
    parser.add_argument("--to", choices=["production"], default="production")
    parser.add_argument(
        "--rollback", action="store_true", help="rollback an archived version instead"
    )
    args = parser.parse_args()

    if args.rollback:
        if not args.version:
            parser.error("--rollback requires --version")
        row = rollback(args.model_name, args.version)
    else:
        row = promote_to_production(args.model_name, args.version)

    print(f"model_name={row.model_name} version={row.version} stage={row.stage}")


if __name__ == "__main__":
    _main()
