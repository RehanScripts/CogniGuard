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
import json
import pathlib

from sqlalchemy import select, update

from app.db import SessionLocal
from app.models.governance import AuditLog, ModelRegistry

# Map benchmark_report.json track keys to model_registry model_name values.
_BENCHMARK_MODEL_MAP: dict[str, str] = {
    "LSTMAutoencoder": "lstm_autoencoder",
    "IsolationForest": "isolation_forest",
    "XGBoost": "xgboost_txn",
    "RandomForest": "isolation_forest",  # best fallback for track1 alt winners
}

_BENCHMARK_REPORT_PATH = pathlib.Path(__file__).parent / "benchmark_report.json"


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


def promote_from_benchmark(report_path: pathlib.Path = _BENCHMARK_REPORT_PATH) -> list[ModelRegistry]:
    """Read benchmark_report.json, resolve the winner per track, and promote each
    to production.  Track1 winner → lstm_autoencoder / isolation_forest;
    track2 winner → xgboost_txn.  Skips a track if no staging row exists."""
    with open(report_path) as f:
        report = json.load(f)

    confirmation = report.get("confirmation", {})
    promoted: list[ModelRegistry] = []
    for _track, benchmark_name in confirmation.items():
        model_name = _BENCHMARK_MODEL_MAP.get(benchmark_name)
        if model_name is None:
            print(f"[promote] no mapping for benchmark winner={benchmark_name!r}, skipping")
            continue
        try:
            row = promote_to_production(model_name)
            promoted.append(row)
            print(f"[promote] {model_name} version={row.version} → production")
        except LookupError as exc:
            print(f"[promote] skipping {model_name}: {exc}")
    return promoted


def _main() -> None:
    parser = argparse.ArgumentParser(description="Promote/rollback a model_registry row.")
    sub = parser.add_subparsers(dest="cmd")

    bench_p = sub.add_parser("from-benchmark", help="promote benchmark winners to production")
    bench_p.add_argument("--report", default=str(_BENCHMARK_REPORT_PATH), dest="report_path")

    manual_p = sub.add_parser("promote", help="promote a specific staging model")
    manual_p.add_argument("--model", required=True, dest="model_name")
    manual_p.add_argument("--version", default=None)

    roll_p = sub.add_parser("rollback", help="rollback an archived version to production")
    roll_p.add_argument("--model", required=True, dest="model_name")
    roll_p.add_argument("--version", required=True)

    # Legacy positional style: python -m training.promote --model X --rollback
    parser.add_argument("--model", default=None, dest="_model")
    parser.add_argument("--version", default=None, dest="_version")
    parser.add_argument("--rollback", action="store_true")

    args = parser.parse_args()

    if args.cmd == "from-benchmark":
        promote_from_benchmark(pathlib.Path(args.report_path))
    elif args.cmd == "promote":
        row = promote_to_production(args.model_name, args.version)
        print(f"model_name={row.model_name} version={row.version} stage={row.stage}")
    elif args.cmd == "rollback":
        row = rollback(args.model_name, args.version)
        print(f"model_name={row.model_name} version={row.version} stage={row.stage}")
    elif args._model:
        # Legacy path
        if args._rollback:
            if not args._version:
                parser.error("--rollback requires --version")
            row = rollback(args._model, args._version)
        else:
            row = promote_to_production(args._model, args._version)
        print(f"model_name={row.model_name} version={row.version} stage={row.stage}")
    else:
        parser.print_help()


if __name__ == "__main__":
    _main()
