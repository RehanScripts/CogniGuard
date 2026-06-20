"""Model/score drift monitor (Implementation.md Phase 12).

No table in this codebase persists historical per-request feature vectors -- Redis is an
ephemeral cache (CLAUDE.md: "rebuildable... not a source of truth") and Flink's S3 mirror
stores raw Kafka event JSON, not derived features. So "feature drift" here runs on the
`risk_scores` table's persisted score columns (`behavior_score`, `transaction_score`,
`final_risk_score`): a live window vs. an older reference window, compared with PSI
(Population Stability Index) and the KS (Kolmogorov-Smirnov) two-sample statistic. This is
the only "online distribution" data that exists without adding new capture infrastructure
Implementation.md's Phase 12 file list doesn't call for.

`outcome_drift()` is precision-only (`confirmed_fraud / (confirmed_fraud + false_positive)`
over resolved cases) -- recall isn't computable in-system, there's no ground truth for
missed/undetected fraud. It's reported alongside the score-drift columns but, since the
policy's `drift` section (see `app.services.policy.DEFAULT_POLICY`) defines no precision
threshold, it never triggers a breach/retrain on its own (CLAUDE.md #6: no thresholds get
hardcoded here either -- if outcome-precision alerting is wanted later, it goes in the
policy first).

A breaching column triggers a retrain of the model(s) that feed it, registered as a new
`stage="staging"` challenger (`register_model(..., stage="staging")`) -- never directly to
`production`, so a drift-triggered retrain still runs in shadow via `app.scoring.shadow`
before anyone promotes it (CLAUDE.md #18).

Runnable standalone:  python -m training.drift_monitor
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any, Sequence

import numpy as np
from scipy import stats
from sqlalchemy import select
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.orm import Session as DbSession

from app.db import SessionLocal
from app.models.governance import Case
from app.models.scoring import RiskScore
from app.services import audit
from app.services.policy import active_policy

logger = logging.getLogger("cogniguard.drift_monitor")

_RESOLVED_LABELS = ("confirmed_fraud", "false_positive")

SCORE_COLUMNS: dict[str, InstrumentedAttribute] = {
    "behavior_score": RiskScore.behavior_score,
    "transaction_score": RiskScore.transaction_score,
    "final_risk_score": RiskScore.final_risk_score,
}
# Which model(s) a breaching column should trigger a staging retrain for. final_risk_score
# is the stacked combination of both, so a breach there retrains both as challengers.
COLUMN_MODELS: dict[str, tuple[str, ...]] = {
    "behavior_score": ("isolation_forest",),
    "transaction_score": ("xgboost_txn",),
    "final_risk_score": ("isolation_forest", "xgboost_txn"),
}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _psi(
    live: np.ndarray, reference: np.ndarray, *, n_bins: int = 10, epsilon: float = 1e-4
) -> float:
    """PSI with bin edges drawn from the reference sample's quantiles -- the standard
    formulation (live bucketed into the reference's own distribution)."""
    edges = np.unique(np.quantile(reference, np.linspace(0, 1, n_bins + 1)))
    if len(edges) < 3:
        return 0.0  # reference has ~zero variance; PSI isn't meaningful here
    edges[0], edges[-1] = -np.inf, np.inf
    ref_counts, _ = np.histogram(reference, bins=edges)
    live_counts, _ = np.histogram(live, bins=edges)
    ref_prop = ref_counts / ref_counts.sum() + epsilon
    live_prop = live_counts / live_counts.sum() + epsilon
    return float(np.sum((live_prop - ref_prop) * np.log(live_prop / ref_prop)))


def score_drift(
    live: Sequence[float], reference: Sequence[float], *, n_bins: int = 10
) -> dict[str, Any]:
    """PSI + KS two-sample stat between a live and a reference sample of one score column."""
    live_arr = np.asarray(live, dtype=float)
    reference_arr = np.asarray(reference, dtype=float)
    ks_result = stats.ks_2samp(live_arr, reference_arr)
    return {
        "psi": _psi(live_arr, reference_arr, n_bins=n_bins),
        "ks_stat": float(ks_result.statistic),
        "ks_pvalue": float(ks_result.pvalue),
        "n_live": int(live_arr.size),
        "n_reference": int(reference_arr.size),
    }


def outcome_drift(db: DbSession, *, since: dt.datetime) -> dict[str, Any]:
    """Precision over cases resolved since `since` -- the only outcome signal available
    without ground truth for undetected (missed) fraud."""
    resolved = db.scalars(
        select(Case.status).where(Case.status.in_(_RESOLVED_LABELS), Case.resolved_at >= since)
    ).all()
    n_confirmed = sum(1 for status in resolved if status == "confirmed_fraud")
    n_false_positive = sum(1 for status in resolved if status == "false_positive")
    n_resolved = n_confirmed + n_false_positive
    return {
        "n_resolved": n_resolved,
        "n_confirmed_fraud": n_confirmed,
        "n_false_positive": n_false_positive,
        "precision": (n_confirmed / n_resolved) if n_resolved else None,
    }


def _column_values(
    db: DbSession, column: InstrumentedAttribute, *, start: dt.datetime, end: dt.datetime
) -> list[float]:
    values = db.scalars(
        select(column).where(
            RiskScore.is_shadow.is_(False),
            RiskScore.scored_at >= start,
            RiskScore.scored_at < end,
            column.is_not(None),
        )
    ).all()
    return [float(v) for v in values]


def run(
    db: DbSession,
    *,
    policy: dict[str, Any],
    lookback_hours: int | None = None,
    reference_hours: int | None = None,
    trigger_retrain: bool = True,
) -> dict[str, Any]:
    drift_policy = policy.get("drift", {})
    lookback_hours = (
        lookback_hours if lookback_hours is not None else drift_policy.get("lookback_hours", 24)
    )
    reference_hours = (
        reference_hours if reference_hours is not None else drift_policy.get("reference_hours", 168)
    )
    min_samples = drift_policy.get("min_samples", 30)
    psi_alert = drift_policy.get("psi_alert", 0.25)
    ks_alert = drift_policy.get("ks_alert", 0.2)

    now = _now()
    live_start = now - dt.timedelta(hours=lookback_hours)
    reference_start = live_start - dt.timedelta(hours=reference_hours)

    columns_report: dict[str, dict[str, Any]] = {}
    breaches: list[dict[str, Any]] = []
    models_to_retrain: set[str] = set()

    for name, column in SCORE_COLUMNS.items():
        live_values = _column_values(db, column, start=live_start, end=now)
        reference_values = _column_values(db, column, start=reference_start, end=live_start)
        if len(live_values) < min_samples or len(reference_values) < min_samples:
            columns_report[name] = {
                "skipped": True,
                "reason": "insufficient_samples",
                "n_live": len(live_values),
                "n_reference": len(reference_values),
            }
            continue

        metrics = score_drift(live_values, reference_values)
        breached = metrics["psi"] >= psi_alert or metrics["ks_stat"] >= ks_alert
        metrics["breached"] = breached
        columns_report[name] = metrics
        if breached:
            breaches.append({"column": name, **metrics})
            models_to_retrain.update(COLUMN_MODELS[name])

    outcome = outcome_drift(db, since=live_start)

    for breach in breaches:
        audit.write_audit_log(
            db,
            actor_type="system",
            actor_id="training.drift_monitor",
            action="DRIFT_BREACH",
            entity_type="model_registry",
            entity_id=None,
            metadata={"models": sorted(COLUMN_MODELS[breach["column"]]), **breach},
        )

    retrained: list[str] = []
    if trigger_retrain and models_to_retrain:
        if "isolation_forest" in models_to_retrain:
            from training import train_isolation_forest

            train_isolation_forest.main(stage="staging")
            retrained.append("isolation_forest")
        if "xgboost_txn" in models_to_retrain:
            from training import train_xgboost

            train_xgboost.main(stage="staging")
            retrained.append("xgboost_txn")

    return {
        "window": {
            "live_start": live_start.isoformat(),
            "live_end": now.isoformat(),
            "reference_start": reference_start.isoformat(),
            "reference_end": live_start.isoformat(),
        },
        "columns": columns_report,
        "outcome": outcome,
        "breaches": breaches,
        "retrained_models": retrained,
    }


def _main() -> None:
    logging.basicConfig(level="INFO")
    with SessionLocal() as db:
        report = run(db, policy=active_policy())
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    _main()
