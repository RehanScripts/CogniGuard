"""Active policy load (Implementation.md Phase 7, CLAUDE.md invariant 6 -- bands,
thresholds, weights, amplifier multipliers, the assurance ladder, and hardening
escalation never get hardcoded in decision logic; they come from here).

There is no `policies` table in the canonical 16-table OLTP schema (PRD §17.1) and
Phase 8's file list doesn't add one either, so persistence here is a `policy:active`
JSON blob in Redis (the same role Redis already plays for nonces/locks/counters) rather
than a new Postgres table -- this is what lets an admin policy edit take effect live,
no restart, without a Postgres read on the scoring hot path. Phase 8's `/admin/policy`
endpoint owns writing that key; this module only needs the read side + safe defaults.
"""

from __future__ import annotations

import copy
import json
from typing import Any

from redis import Redis

POLICY_REDIS_KEY = "policy:active"

DEFAULT_POLICY: dict[str, Any] = {
    "scoring_mode": "stacked",  # "stacked" | "weighted" -- never run both (CLAUDE.md #5)
    "weights": {"transaction": 0.60, "behavior": 0.25, "device": 0.15},  # weighted-mode only
    "thresholds": {"low_max": 30, "medium_max": 60, "very_high_min": 85},
    # Per-action-type stakes classification feeding the risk×action matrix (PRD §10.2).
    # "login" defaults to "medium" -- PRD §10.1's band ladder (no stakes column) is
    # exactly §10.2's medium-stakes column.
    "action_sensitivity": {
        "login": {"stakes": "medium"},
        "view_balance": {"stakes": "low"},
        "add_payee": {"stakes": "medium"},
        "transfer_known_payee_small": {"stakes": "medium"},
        "transfer_new_payee_large": {"stakes": "high"},
        "change_contact": {"stakes": "high"},
        "raise_limit": {"stakes": "high"},
    },
    "amplifiers": {
        "NEW_BENEF_HIGHVAL": 1.5,
        "AMOUNT_SPIKE": 1.4,
        "RAPID_FANOUT": 1.4,
        "DRAIN": 1.3,
        "COERCION_TIME": 1.2,
    },
    # Assurance-ordered step-up ladder (PRD §10.1).
    # "light" (medium risk): single factor — OTP / MPIN.
    # "strong" (high risk): sequential two-factor — OTP first, then biometric.
    #   adaptive_auth.select_factor will use OTP as challenge_type and set
    #   second_factor=FINGERPRINT/PASSKEY for the sequential Android 2FA flow.
    #   VOICE_READBACK left in the strong ladder as fallback when no biometric available.
    "stepup": {
        "light": ["MPIN", "OTP"],
        "strong": ["OTP", "FINGERPRINT", "PASSKEY", "VOICE_READBACK"],
        # Failed step-up attempts allowed before login escalates to block + alert
        # (PRD §10.1 "if fail -> Blocked"). Admin-tunable like every other policy knob.
        "max_attempts": 3,
    },
    # Per-user continuous identity verification (Implementation.md Phase 20-22). All
    # Trust-Score weights live here, never hardcoded in the scorer (CLAUDE.md invariant 6).
    # `support` weights (genuineness=AE / device / env) sum to 1 and form the supporting
    # composite; identity match is the multiplicative anchor over it. `env_penalty` is how
    # much each anomalous-context flag subtracts from env-consistency.
    "trust_weights": {
        "support": {"genuineness": 0.5, "device": 0.3, "env": 0.2},
        "env_penalty": {"geo_change": 0.4, "new_device": 0.4, "vpn": 0.2},
        "embedding_sim_weight": 0.25,  # F4: blend weight for cosine similarity in behavior_match
    },
    # Data-driven enrollment: a user is enrolled (identity gate active) only after this
    # many genuine login/app-open cycles; until then trust = support composite only,
    # biased to verify, never block (CLAUDE.md invariant 9).
    "enrollment": {"min_sessions": 10},
    "cooling_off": {"minutes": 30, "reconfirm_channel": "APP_PUSH"},
    "hardening": {"delay_after": 3, "captcha_after": 4, "lock_after": 5, "lock_minutes": 15},
    # Phase 12 drift_monitor breach thresholds (Implementation.md §12) -- PSI/KS on the
    # risk_scores score columns, live window vs. an older reference window, plus outcome
    # precision over resolved cases. Never hardcoded in drift_monitor.py (CLAUDE.md #6).
    "drift": {
        "psi_alert": 0.25,
        "ks_alert": 0.2,
        "lookback_hours": 24,
        "reference_hours": 168,
        "min_samples": 30,
    },
    # Device-trust budget constants (UPGRADE_PLAN.md Phase B4). All caps used
    # in device_trust.py become policy-readable so an admin can tune them live
    # without redeploying; device_trust.compute() falls back to these defaults
    # when the key is absent (backward compat, degraded-Redis fallback).
    "device_trust": {
        "rooted_ceiling": 10.0,  # hard cap — rooted/emulator can never look clean
        "base_new": 35.0,  # first time we see this device fingerprint
        "base_known": 75.0,  # device fingerprint seen before for this user
        "penalty_impossible_travel": 40.0,
        "bonus_biometric": 15.0,
        "impossible_travel_kmh": 800.0,
    },
}


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> None:
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def active_policy(redis: Redis | None = None) -> dict[str, Any]:
    """The active policy: `DEFAULT_POLICY` overlaid with the admin-edited
    `policy:active` Redis blob, if any. Never raises -- a missing/empty/unreadable
    key, or a degraded Redis, just falls back to defaults (NFR-4 graceful degradation)."""
    policy = copy.deepcopy(DEFAULT_POLICY)
    if redis is None:
        return policy
    try:
        raw = redis.get(POLICY_REDIS_KEY)
    except Exception:
        return policy
    if not raw:
        return policy
    try:
        overlay = json.loads(raw)
    except (TypeError, ValueError):
        return policy
    if isinstance(overlay, dict):
        _deep_merge(policy, overlay)
    return policy
