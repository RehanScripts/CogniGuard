"""Orchestrate IF -> XGBoost (stacked, default) or the weighted-ensemble alternative --
never both (CLAUDE.md invariant 5). Implementation.md Phase 6 pseudocode, filled in.

Behavior_Score itself is AE-primary / IF-shadow / fallback (Implementation.md Phase 15):
the LSTM Autoencoder drives `bscore` whenever a usable sequence/recon-error is available
and the bundle isn't AE-cold-start; Isolation Forest is *always* computed too (logged as
`if_shadow_score`, never acted on once AE is live) and is what cold-start and AE failures
fall back to. Everything from this point on -- XGBoost, amplifiers, bands, reason codes --
only ever sees the resulting single `bscore` and has no idea which model produced it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from redis import Redis

from ..schemas.features import FeatureBundle
from ..schemas.scoring import Amplifier, RiskBand, ScoreResult
from . import amplifiers, autoencoder, calibration, explain, isolation_forest, xgboost_model
from .amplifiers import TxnContext
from .registry import Registry


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass
class ScoreProvenance:
    source: str  # "if" | "ae" | "fallback"
    degraded: bool
    if_shadow_score: float | None = None
    ae_recon_error: float | None = None


def _if_shadow(
    bundle: FeatureBundle, *, registry: Registry, redis: Redis | None
) -> tuple[float, bool]:
    """Always computed, regardless of which source ends up driving `bscore` -- IF is
    both the cold-start/degradation fallback and a permanent shadow signal once AE is
    primary. Returns `(score, ok)`; `ok=False` on any load/inference failure."""
    try:
        if_loaded = registry.get("isolation_forest")
        baseline = (
            isolation_forest.load_baseline(bundle.user_id, redis=redis)
            if redis is not None
            else None
        )
        score = isolation_forest.behavior_score(
            bundle.behavior_vector(), model=if_loaded.model, baseline=baseline
        )
        return score, True
    except Exception:
        return 0.0, False


def _ae_available(bundle: FeatureBundle) -> bool:
    return bundle.ae_recon_error is not None or bundle.behavior_sequence is not None


def _ae_primary(
    bundle: FeatureBundle, *, registry: Registry, redis: Redis | None
) -> tuple[float, float]:
    """`(ae_score, recon_error)`. Raises on any failure -- the caller treats that as an
    AE failure and falls back to the IF-shadow score. Mobile already carries its own
    device-computed `ae_recon_error` and skips model inference entirely; web assembles
    `recon_error` from the Redis-backed rolling window via the injected ONNX session."""
    calib = calibration.load_calibration(bundle.user_id, redis=redis)
    if bundle.ae_recon_error is not None:
        recon_error = bundle.ae_recon_error
    else:
        ae_loaded = registry.get("lstm_autoencoder")
        recon_error = autoencoder.reconstruction_error(
            bundle.behavior_sequence, model=ae_loaded.model, mask=bundle.behavior_sequence_mask
        )
    return calibration.calibrate_ae(recon_error, calib), recon_error


def _behavior_score(
    bundle: FeatureBundle, *, registry: Registry, redis: Redis | None
) -> tuple[float, ScoreProvenance]:
    """AE-primary / IF-shadow / fallback routing (Implementation.md Phase 15). A bundle
    with no AE input at all (`behavior_sequence` and `ae_recon_error` both unset -- every
    pre-Phase-15 caller that never wires `session_id`, and every hand-built bundle in
    the Phase 6 baseline tests) is treated the same as an explicit `ae_cold_start`:
    there's nothing to run AE on, which is "no signal yet," not a failure."""
    if_score, if_ok = _if_shadow(bundle, registry=registry, redis=redis)
    if_shadow_score = if_score if if_ok else None

    if bundle.ae_cold_start or not _ae_available(bundle):
        return if_score, ScoreProvenance(
            source="if" if if_ok else "fallback",
            degraded=not if_ok,
            if_shadow_score=if_shadow_score,
        )
    try:
        ae_score, recon_error = _ae_primary(bundle, registry=registry, redis=redis)
        return ae_score, ScoreProvenance(
            source="ae",
            degraded=False,
            if_shadow_score=if_shadow_score,
            ae_recon_error=recon_error,
        )
    except Exception:
        return (if_score if if_ok else 0.0), ScoreProvenance(
            source="if" if if_ok else "fallback",
            degraded=True,
            if_shadow_score=if_shadow_score,
        )


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
    bscore, provenance = _behavior_score(bundle, registry=registry, redis=redis)
    degraded = provenance.degraded

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
    ae_reason = explain.ae_anomaly_reason(provenance.ae_recon_error, bscore)
    if ae_reason is not None:
        reasons.append(ae_reason)

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
        behavior_score_source=provenance.source,
        if_shadow_score=provenance.if_shadow_score,
        ae_recon_error=provenance.ae_recon_error,
    )
