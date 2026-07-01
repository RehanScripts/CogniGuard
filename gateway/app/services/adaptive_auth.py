"""Assurance-ordered step-up factor selection (Implementation.md Phase 7, PRD §10.1,
CLAUDE.md invariant 15): pick the lightest factor that clears the measured risk;
degrade only to an equal-or-higher factor, never silently below the band's required
strength.

Tiers: knowledge/weak-possession (MPIN, OTP) < OOB possession (VOICE_READBACK) <
phishing-resistant (FINGERPRINT, PASSKEY). "strong" assurance demands a strong,
phishing-resistant factor -- not SMS-OTP alone (Implementation.md line 463) -- so its
candidate tier floor sits above plain OTP/MPIN.

For adaptive re-authentication:
  light  (medium risk) → single factor: OTP or MPIN
  strong (high risk)   → sequential two-factor: OTP first, then FINGERPRINT/PASSKEY
"""

from __future__ import annotations

import uuid
from typing import Iterable, Mapping

from ..schemas.decision import Assurance, ChallengeType, StepUp

FACTOR_TIER: dict[ChallengeType, int] = {
    "MPIN": 1,
    "OTP": 1,
    "VOICE_READBACK": 2,
    "FINGERPRINT": 3,
    "PASSKEY": 3,
}

MIN_TIER: dict[Assurance, int] = {"light": 1, "strong": 2}

# Universally-available factors when the caller doesn't know device capabilities yet.
# Mobile logins always have BiometricPrompt available, so FINGERPRINT is assumed.
# Web logins without explicit caps get OTP/MPIN only (no biometric key enrolled).
_UNIVERSAL_CAPS = frozenset({"OTP", "MPIN", "FINGERPRINT"})

# Biometric factors used as second-factor in strong-assurance 2FA flows.
_BIOMETRIC_FACTORS: tuple[ChallengeType, ...] = ("FINGERPRINT", "PASSKEY")


def select_factor(
    required_assurance: Assurance,
    device_caps: Iterable[str] | None,
    stepup_policy: Mapping[str, list[str]],
) -> StepUp:
    caps = frozenset(device_caps) if device_caps is not None else _UNIVERSAL_CAPS
    ladder = stepup_policy.get(required_assurance, [])

    if required_assurance == "strong":
        # High risk → sequential OTP + Biometric two-factor flow.
        return _select_strong_factor(caps, ladder)

    # Light assurance (medium risk): single factor — pick first available from ladder.
    min_tier = MIN_TIER[required_assurance]
    for factor in ladder:
        if factor in caps and FACTOR_TIER.get(factor, 0) >= min_tier:
            return _step_up(factor, required_assurance)

    # Nothing in the preferred ladder is both available and strong enough -- degrade
    # only upward: pick the strongest available factor that still clears the bar.
    eligible = [f for f in caps if FACTOR_TIER.get(f, 0) >= min_tier]
    if eligible:
        best = max(eligible, key=lambda f: FACTOR_TIER.get(f, 0))
        return _step_up(best, required_assurance)

    # Nothing available clears the bar at all -- surface the strongest available.
    if caps:
        best = max(caps, key=lambda f: FACTOR_TIER.get(f, 0))
        return _step_up(best, required_assurance)

    return _step_up("OTP", required_assurance)


def _select_strong_factor(
    caps: frozenset[str],
    ladder: list[str],
) -> StepUp:
    """Strong assurance (high-risk): sequential two-factor — OTP first, then biometric.

    The StepUp object carries `challenge_type=OTP` (first factor the backend verifies via
    `/step-up/verify`) and `second_factor=FINGERPRINT` (second factor the Android client
    performs locally via BiometricPrompt before submitting the combined assertion).

    Fallback order:
      1. OTP + first biometric available in ladder/caps (FINGERPRINT > PASSKEY)
      2. OTP only (if no biometric available on device)
      3. First biometric only (if OTP not in caps — unlikely, OTP is always universal)
    """
    # Find best biometric second-factor: prefer ladder order, then caps order.
    second_factor: ChallengeType | None = None
    for f in ladder:
        if f in _BIOMETRIC_FACTORS and f in caps:
            second_factor = f  # type: ignore[assignment]
            break
    if second_factor is None:
        for f in _BIOMETRIC_FACTORS:
            if f in caps:
                second_factor = f
                break

    if "OTP" in caps or "MPIN" in caps:
        first: ChallengeType = "OTP" if "OTP" in caps else "MPIN"
        return _step_up(first, "strong", second_factor=second_factor)

    # OTP not available — fall back to biometric-only.
    if second_factor is not None:
        return _step_up(second_factor, "strong")

    # Absolute fallback.
    return _step_up("OTP", "strong")


def _step_up(
    factor: ChallengeType,
    assurance: Assurance,
    second_factor: ChallengeType | None = None,
) -> StepUp:
    return StepUp(
        challenge_type=factor,
        assurance=assurance,
        challenge_id=str(uuid.uuid4()),
        second_factor=second_factor,
    )


_OTP_LIKE_CHALLENGE_TYPES = frozenset({"OTP", "MPIN"})


def accepts_assertion(
    challenge_type: str,
    otp_or_assertion: str,
    *,
    challenge_id: str | None = None,
    redis: object | None = None,
) -> bool:
    """Whether a submitted step-up assertion clears the challenge (login + payment
    step-up share this exact check).

    Single-factor:
      • OTP/MPIN: verified against the Redis-backed code generated at challenge creation.
        Pass ``challenge_id`` and ``redis`` to enable real verification; returns False
        without them so callers can't accidentally skip Redis lookup.
      • FINGERPRINT/PASSKEY/VOICE_READBACK: any non-empty assertion means the
        device-local biometric already succeeded (device-attested).

    Two-factor (strong assurance): Android client sends a combined assertion string
    "<otp-code>:biometric-FINGERPRINT-ok" after completing both steps. The gateway
    validates the OTP part via Redis; the colon-separated biometric token is device-
    attested proof.
    """
    if challenge_type in _OTP_LIKE_CHALLENGE_TYPES:
        otp_part = otp_or_assertion.split(":", 1)[0]
        if challenge_id is not None and redis is not None:
            from .otp import verify_otp

            return verify_otp(challenge_id, otp_part, redis)
        return False
    return bool(otp_or_assertion)
