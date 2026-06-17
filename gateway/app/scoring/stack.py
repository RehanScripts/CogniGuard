"""Orchestrate IF -> XGBoost (stacked, default) or the weighted-ensemble alternative --
never both (CLAUDE.md invariant 5). Implementation.md Phase 6 pseudocode, filled in.
"""

from __future__ import annotations

from typing import Any, Mapping

from redis import Redis

from ..schemas.features import FeatureBundle
from ..schemas.scoring import Amplifier, RiskBand, ScoreResult
from . import amplifiers, explain, isolation_forest, xgboost_model
from .amplifiers import TxnContext
from .registry import Registry


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def map_band(score: float, thresholds: Mapping[str, float]) -> RiskBand:
    if score < thresholds["low_max"]:
        return "low"
    if score < thresholds["medium_max"]:
        return "medium"
    if score >= thresholds["very_high_min"]:
        return "very_high"
    return "high"


def fallback_rule_score(bundle: FeatureBundle, bscore: float) -> float:
    """IF + decision-layer rules (NFR-4) when XGBoost is unavailable. Deliberately
    conservative: weights bscore the most, adds small fixed bumps per fired
    decision-layer trigger. Excludes any bump for cold_start itself -- a brand-new user
    with otherwise-clean signals must stay low/verify-band, never very_high purely from
    being new (CLAUDE.md invariant 9)."""
    score = 0.35 * bscore
    if bundle.device.is_new_device:
        score += 0.10
    if bundle.network.geo_change:
        score += 0.15
    if bundle.txn.high_velocity:
        score += 0.15
    if bundle.txn.is_new_payee:
        score += 0.10
    if bundle.txn.odd_time:
        score += 0.05
    return _clamp(score, 0.0, 1.0)


def score(
    bundle: FeatureBundle,
    *,
    policy: Mapping[str, Any],
    registry: Registry,
    txn_context: TxnContext | None = None,
    redis: Redis | None = None,
) -> ScoreResult:
    degraded = False

    try:
        if_loaded = registry.get("isolation_forest")
        baseline = (
            isolation_forest.load_baseline(bundle.user_id, redis=redis)
            if redis is not None
            else None
        )
        bscore = isolation_forest.behavior_score(
            bundle.behavior_vector(), model=if_loaded.model, baseline=baseline
        )
    except Exception:
        bscore, degraded = 0.0, True

    feats = bundle.xgb_features(behavior_score=bscore)

    if policy.get("scoring_mode", "stacked") == "weighted":
        # §9.2 weighted-ensemble alternative -- never run alongside stacked.
        device_signal = bundle.device.device_trust / 100.0 if bundle.device.device_trust else 0.0
        try:
            xgb_loaded = registry.get("xgboost_txn")
            txn_p = xgboost_model.fraud_probability(feats, model=xgb_loaded.model)
            model_version = xgb_loaded.version
        except Exception:
            degraded = True
            txn_p = fallback_rule_score(bundle, bscore)
            model_version = "fallback"
        final_p = _clamp(0.60 * txn_p + 0.25 * bscore + 0.15 * (1 - device_signal), 0, 1)
    else:
        try:
            xgb_loaded = registry.get("xgboost_txn")
            final_p = xgboost_model.fraud_probability(feats, model=xgb_loaded.model)
            model_version = xgb_loaded.version
        except Exception:
            degraded = True
            final_p = fallback_rule_score(bundle, bscore)
            model_version = "fallback"

    base = round(100 * _clamp(final_p, 0, 1), 1)
    amps: list[Amplifier] = []
    final_score = base
    if txn_context is not None:
        amps = amplifiers.evaluate(txn_context, policy["amplifiers"])
        final_score = amplifiers.apply(base, amps)

    band = map_band(final_score, policy["thresholds"])
    reasons = explain.reason_codes(bundle, base_drivers=True) + [a.as_reason() for a in amps]

    return ScoreResult(
        behavior_score=bscore,
        transaction_score=final_p,
        final_risk_score=final_score,
        base_score=base,
        risk_band=band,
        model_version=model_version,
        amplifiers=amps,
        reason_codes=reasons,
        degraded_mode=degraded,
    )
