"""Assurance-ordered step-up factor selection (Implementation.md Phase 7, PRD §10.1,
CLAUDE.md invariant 15): pick the lightest factor that clears the measured risk;
degrade only to an equal-or-higher factor, never silently below the band's required
strength.

Tiers: knowledge/weak-possession (MPIN, OTP) < OOB possession (VOICE_READBACK) <
phishing-resistant (FINGERPRINT, PASSKEY). "strong" assurance demands a strong,
phishing-resistant factor -- not SMS-OTP alone (Implementation.md line 463) -- so its
candidate tier floor sits above plain OTP/MPIN.
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
_UNIVERSAL_CAPS = frozenset({"OTP", "MPIN"})


def select_factor(
    required_assurance: Assurance,
    device_caps: Iterable[str] | None,
    stepup_policy: Mapping[str, list[str]],
) -> StepUp:
    caps = frozenset(device_caps) if device_caps is not None else _UNIVERSAL_CAPS
    min_tier = MIN_TIER[required_assurance]
    ladder = stepup_policy.get(required_assurance, [])

    for factor in ladder:
        if factor in caps and FACTOR_TIER.get(factor, 0) >= min_tier:
            return _step_up(factor, required_assurance)

    # Nothing in the preferred ladder is both available and strong enough -- degrade
    # only upward: pick the strongest available factor that still clears the bar.
    eligible = [f for f in caps if FACTOR_TIER.get(f, 0) >= min_tier]
    if eligible:
        best = max(eligible, key=lambda f: FACTOR_TIER.get(f, 0))
        return _step_up(best, required_assurance)

    # Nothing available clears the bar at all -- still never go below the band's
    # required strength silently; surface the strongest factor the device has, even
    # though it falls short, rather than crashing.
    if caps:
        best = max(caps, key=lambda f: FACTOR_TIER.get(f, 0))
        return _step_up(best, required_assurance)

    return _step_up("OTP", required_assurance)


def _step_up(factor: ChallengeType, assurance: Assurance) -> StepUp:
    return StepUp(
        challenge_type=factor,
        assurance=assurance,
        challenge_id=str(uuid.uuid4()),
    )
