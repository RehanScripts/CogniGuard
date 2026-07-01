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

import logging
from dataclasses import dataclass
from typing import Any, Mapping

from redis import Redis

from ..schemas.features import FeatureBundle
from ..schemas.scoring import Amplifier, ReasonCode, RiskBand, ScoreResult
from . import (
    amplifiers,
    autoencoder,
    calibration,
    explain,
    identity,
    isolation_forest,
    xgboost_model,
)
from .amplifiers import TxnContext
from .registry import Registry

_logger = logging.getLogger("cogniguard.scoring")


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
    `recon_error` from the Redis-backed rolling window via the injected ONNX session.

    Mobile errors (13k-20k) and web errors (~0.01-0.1) live in completely different
    numeric ranges because Android's soft-keyboard gives hold_time=0 (vs CMU ~100ms),
    real swipe_velocity vs zero in CMU training data, etc. They must use separate
    calibration keys so mobile doesn't saturate the web population calibration."""
    if bundle.ae_recon_error is not None:
        # Mobile path: on-device TFLite error, use mobile-specific calibration
        calib = calibration.load_mobile_calibration(bundle.user_id, redis=redis)
        return calibration.calibrate_ae(bundle.ae_recon_error, calib), bundle.ae_recon_error
    # Web path: compute via ONNX session, use web calibration
    calib = calibration.load_calibration(bundle.user_id, redis=redis)
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


def map_band_adaptive(
    score: float,
    thresholds: Mapping[str, float],
    risk_baseline: dict | None = None,
) -> RiskBand:
    """Adaptive band mapping using per-user risk baseline (Phase B4).

    When ≥20 clean low-risk sessions have been recorded, derive tighter thresholds
    around the user's historical average ± σ; clamp to 70–130% of global policy
    thresholds so the adaptive window can never collapse to a trivial range or open
    a back-door to high-risk users. Falls back to global policy when no baseline.
    """
    if risk_baseline and risk_baseline.get("count", 0) >= 20:
        avg = float(risk_baseline["avg"])
        std = max(float(risk_baseline["std"]), 1.0)  # prevent zero-variance collapse
        low_max = _clamp(
            avg - std,
            thresholds["low_max"] * 0.7,
            thresholds["low_max"] * 1.3,
        )
        medium_max = _clamp(
            avg + 1.5 * std,
            thresholds["medium_max"] * 0.7,
            thresholds["medium_max"] * 1.3,
        )
        very_high_min = _clamp(
            avg + 3.0 * std,
            thresholds["very_high_min"] * 0.7,
            thresholds["very_high_min"] * 1.3,
        )
        return map_band(
            score,
            {"low_max": low_max, "medium_max": medium_max, "very_high_min": very_high_min},
        )
    return map_band(score, thresholds)


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
    txn_final = base
    if txn_context is not None:
        amps = amplifiers.evaluate(txn_context, policy["amplifiers"])
        txn_final = amplifiers.apply(base, amps)

    # --- Continuous identity verification (Implementation.md Phase 20-22) -------------
    # AE stays primary/active: `bscore` (AE-primary, IF-shadow/fallback) is BOTH fed to
    # XGBoost above AND reused here as the genuineness term -- identity is ADDED alongside
    # the AE, never instead of it (CLAUDE.md invariant 5). All weights come from policy.
    trust_weights = policy.get("trust_weights", {})
    genuineness = 100.0 * (1.0 - bscore)
    # For enrolled users in AE cold-start the scorer is IF (global population model, not
    # per-user).  IF gives bscore≈0.5 for most genuine humans → genuineness≈50%, which
    # means even perfect typing can never reach low-risk trust.  Once the user is enrolled
    # their identity_baseline IS the per-user truth, so substitute behavior_match (computed
    # below) as the genuineness signal when the AE hasn't warmed up yet.  This is computed
    # after behavior_match is known and re-injected into compute_trust.
    _use_bm_as_genuineness = bundle.enrolled and bundle.ae_cold_start
    env_consistency = identity.env_consistency(
        geo_change=bundle.network.geo_change,
        new_device=bundle.device.is_new_device,
        vpn=bundle.network.vpn,
        weights=trust_weights.get("env_penalty", {}),
    )
    behavior_match: float | None = None
    if bundle.enrolled and bundle.identity_baseline is not None:
        behavior_match = identity.behavior_match_score(
            bundle.behavior_vector(), bundle.identity_baseline
        )
    # F4: Blend in embedding cosine similarity when available (warm centroid from prior
    # clean sessions). Weighted average with the robust-z match score — embedding sim
    # provides a complementary global-structure similarity beyond per-feature z distances.
    if behavior_match is not None and bundle.embedding_sim is not None:
        embed_weight = trust_weights.get("embedding_sim_weight", 0.25)
        behavior_match = (1.0 - embed_weight) * behavior_match + embed_weight * (
            bundle.embedding_sim * 100.0
        )
    # Substitute behavior_match as genuineness for enrolled AE cold-start (see comment
    # above where _use_bm_as_genuineness is set).
    effective_genuineness = (
        behavior_match if (_use_bm_as_genuineness and behavior_match is not None) else genuineness
    )
    trust = identity.compute_trust(
        behavior_match=behavior_match,
        genuineness=effective_genuineness,
        device_trust=bundle.device.device_trust,
        env_consistency=env_consistency,
        support_weights=trust_weights.get("support", {}),
    )

    # The identity gate drives the acted-on score only once the user is ENROLLED; until
    # then behavior is exactly as before (XGBoost/IF + amplifiers), cold-start biased to
    # `verify` by the decision engine (CLAUDE.md invariant 9). Once enrolled:
    #
    #   login, 0 failures  → bypass identity gate; use XGBoost/IF score (→ low for genuine
    #                         enrolled user on first-try correct password). Identity gate is
    #                         reserved for suspicious sessions where failures already signal
    #                         credential probing or coercion.
    #   login, ≥1 failure  → identity gate active, band floors anchored to policy thresholds
    #                         so the band is guaranteed regardless of base identity_risk:
    #                           1 wrong  → floor = low_max+5   (≥35 → medium guaranteed)
    #                           2 wrong  → floor = medium_max+2 (≥62 → high guaranteed)
    #                           3 wrong  → floor = medium_max+5 (≥65 → high, not very_high)
    #                           4+ wrong → floor = very_high_min+1 (→ very_high)
    #   payment            → max(identity_risk, txn risk after amplifiers). AE/XGBoost stay
    #                         active for APP-fraud/coercion; identity mismatch still escalates.
    #
    # NOTE: the identity gate stays active even at n=0 -- a correct password on the first
    # try tells us nothing about whether the *typing* behind it was the enrolled user's.
    # Bypassing the gate there would let a stolen-credential login with mismatched
    # behavior score "low" and sail through allow, which is exactly the account-takeover
    # scenario per-user identity verification exists to catch (docs/architecture.md
    # invariant: continuous re-scoring augments, but does not replace, the login check).
    _failure_reason: ReasonCode | None = None
    if behavior_match is not None:
        if txn_context is None:
            n = bundle.login_failure_count
            identity_risk = trust.identity_risk
            if n > 0:
                t = policy["thresholds"]
                lo = t.get("low_max", 30)
                med = t.get("medium_max", 60)
                vh = t.get("very_high_min", 85)
                # Both floor AND ceiling per failure count so the band is guaranteed
                # regardless of what the actual identity_risk is on a given day:
                #   n=1 → [lo+5 .. med-1]  = [35..59]  → always medium
                #   n=2 → [med+2 .. vh-1]  = [62..84]  → always high
                #   n=3 → [med+5 .. vh-1]  = [65..84]  → always high
                #   n=4+ → [vh+1 .. 100]   = [86..100] → always very_high
                _floor = {1: lo + 5, 2: med + 2, 3: med + 5}.get(n, vh + 1)
                _ceil = {1: med - 1, 2: vh - 1, 3: vh - 1}.get(n, 100.0)
                _amp = {1: 1.0, 2: 1.4, 3: 1.5}.get(n, 2.2)
                identity_risk = _clamp(
                    max(round(trust.identity_risk * _amp, 1), float(_floor)), 0.0, float(_ceil)
                )
                _failure_reason = ReasonCode(
                    code="LOGIN_FAILURE_HISTORY",
                    signal=f"{n} failed attempt(s) before this login",
                )
            final_score = identity_risk
        else:
            # Payment: identity gate always active; failures add extra pressure
            identity_risk = trust.identity_risk
            if bundle.login_failure_count > 0:
                _amp = min(1.0 + bundle.login_failure_count * 0.5, 2.0)
                identity_risk = _clamp(round(identity_risk * _amp, 1), 0.0, 100.0)
                _failure_reason = ReasonCode(
                    code="LOGIN_FAILURE_HISTORY",
                    signal=f"{bundle.login_failure_count} failed attempt(s) before this login",
                )
            final_score = max(identity_risk, txn_final)
    else:
        final_score = txn_final

    band = map_band_adaptive(final_score, policy["thresholds"], bundle.risk_baseline)
    reasons = explain.reason_codes(bundle, base_drivers=True) + [a.as_reason() for a in amps]
    if _failure_reason is not None:
        reasons.append(_failure_reason)
    ae_reason = explain.ae_anomaly_reason(provenance.ae_recon_error, bscore)
    if ae_reason is not None:
        reasons.append(ae_reason)
    identity_reason = explain.identity_reason(behavior_match, policy["thresholds"])
    if identity_reason is not None:
        reasons.append(identity_reason)

    _logger.info(
        "scored entity=%s behavior_score_source=%s ae_recon_error=%s if_shadow_score=%s "
        "behavior_score=%.2f behavior_match=%s trust_score=%.1f final_risk_score=%.2f "
        "band=%s model_version=%s degraded=%s",
        "transaction" if txn_context is not None else "login",
        provenance.source,
        provenance.ae_recon_error,
        provenance.if_shadow_score,
        bscore,
        behavior_match,
        trust.trust_score,
        final_score,
        band,
        model_version,
        degraded,
    )
    return ScoreResult(
        behavior_score=bscore,
        device_score=bundle.device.device_trust,
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
        trust_score=trust.trust_score,
        behavior_match_score=behavior_match,
        identity_risk=trust.identity_risk,
    )
