"""Deterministic top-deviation reason-code explainer (NFR-7) -- NOT SHAP/LIME.

z = (x-mean)/max(std,EPS) per BehaviorFeatures dim vs. a fixed global reference, top-2
|z| drivers mapped to plain English via a phrase dict, plus device/geo/txn pseudo-feature
codes. Pure function, no I/O, so it trivially runs inside the latency budget and Phase
6's tests need no live Redis/Postgres. This is deliberately NOT the per-user
behavior:{id}:baseline that isolation_forest.py uses for scoring -- that one needs
scoring accuracy; this one only needs to rank "which dims look unusual" for a
human-readable explanation.

Fired amplifiers are appended separately by stack.py via Amplifier.as_reason() -- not
this module's concern.
"""

from __future__ import annotations

from ..schemas.features import FeatureBundle
from ..schemas.scoring import ReasonCode

EPS = 1e-9

_BEHAVIOR_REFERENCE: dict[str, tuple[float, float]] = {
    "typing_speed": (4.5, 1.5),
    "key_latency_avg": (180.0, 60.0),
    "typing_rhythm_std": (40.0, 20.0),
    "hold_time_avg": (90.0, 30.0),
    "swipe_velocity_norm": (1.2, 0.5),
    "swipe_angle_dev": (0.3, 0.15),
    "touch_pressure_avg": (0.5, 0.2),
    "acceleration_variance": (0.05, 0.03),
    "mouse_velocity_mean": (0.8, 0.4),
}

_PHRASES: dict[str, str] = {
    "typing_speed": "Typing speed differs sharply from the usual pattern",
    "key_latency_avg": "Key-press timing differs sharply from the usual pattern",
    "typing_rhythm_std": "Typing rhythm is unusually irregular",
    "hold_time_avg": "Key hold duration differs sharply from the usual pattern",
    "swipe_velocity_norm": "Swipe speed differs sharply from the usual pattern",
    "swipe_angle_dev": "Swipe direction is unusually inconsistent",
    "touch_pressure_avg": "Touch pressure differs sharply from the usual pattern",
    "acceleration_variance": "Device motion differs sharply from the usual pattern",
    "mouse_velocity_mean": "Mouse movement speed differs sharply from the usual pattern",
}


def _top_drivers(bundle: FeatureBundle, top_n: int = 2) -> list[ReasonCode]:
    scored = []
    for name, (mean, std) in _BEHAVIOR_REFERENCE.items():
        x = getattr(bundle.behavior, name)
        z = (x - mean) / max(std, EPS)
        scored.append((abs(z), name, z))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [
        ReasonCode(code=f"DEVIATION_{name.upper()}", detail=_PHRASES[name], sigma=round(z, 2))
        for _, name, z in scored[:top_n]
    ]


def _pseudo_features(bundle: FeatureBundle) -> list[ReasonCode]:
    out: list[ReasonCode] = []
    if bundle.device.is_new_device:
        out.append(
            ReasonCode(code="NEW_DEVICE", detail="Login/transaction from a device not seen before")
        )
    if bundle.network.geo_change:
        out.append(
            ReasonCode(code="GEO_CHANGE", detail="Location differs from the user's known locations")
        )
    if bundle.txn.is_new_payee:
        out.append(ReasonCode(code="NEW_PAYEE", detail="Transfer to a beneficiary not seen before"))
    if bundle.txn.odd_time:
        out.append(ReasonCode(code="ODD_TIME", detail="Activity outside the user's typical hours"))
    if bundle.txn.high_velocity:
        out.append(ReasonCode(code="HIGH_VELOCITY", detail="Unusually high transaction frequency"))
    return out


def reason_codes(bundle: FeatureBundle, *, base_drivers: bool = True) -> list[ReasonCode]:
    """Deterministic explanation for the base (pre-amplifier) score: top-2 behavioral
    deviation drivers + fired decision-layer pseudo-features."""
    out: list[ReasonCode] = []
    if base_drivers:
        out.extend(_top_drivers(bundle))
    out.extend(_pseudo_features(bundle))
    return out


def ae_anomaly_reason(ae_recon_error: float | None, bscore: float) -> ReasonCode | None:
    """Fires only when the LSTM Autoencoder actually drove `bscore` (Implementation.md
    Phase 15 -- `ae_recon_error` is only set on that path, never on the IF/fallback
    paths) and the calibrated score is above the neutral midpoint `calibration.py`
    anchors `threshold` to (`> 0.5`, the same anchor used everywhere else)."""
    if ae_recon_error is None or bscore <= 0.5:
        return None
    return ReasonCode(
        code="BEHAVIOR_AE_ANOMALY",
        detail="Behavioral sequence reconstruction error exceeds the calibrated threshold",
        sigma=round(bscore, 2),
    )
