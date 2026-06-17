"""Band + risk×action -> allow/verify/block (Implementation.md Phase 7, PRD §10.1/§10.2).

Takes the `risk_band` already computed by `app.scoring.stack.score()` (via
`policy["thresholds"]`) and the stakes of the attempted action, and resolves the
concrete action. Pure function, no I/O -- runs well inside the decision-layer latency
budget (≤30ms login / ≤60ms payment, Architecture §6.1/§6.2).
"""

from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel

from ..schemas.decision import Action, ActionSensitivity, Assurance
from ..schemas.scoring import RiskBand

# PRD §10.2 risk×action matrix, transcribed verbatim. This is structural PRD logic (the
# shape of the matrix itself), not an admin-tunable number like thresholds/weights/
# amplifier multipliers (CLAUDE.md #6 lists those specifically) -- Implementation.md's
# own pseudocode treats it the same way, as a plain constant the engine looks up.
# `very_high` is handled separately in `decide()` (always block+alert, PRD §10.1),
# not part of this matrix.
RISK_ACTION_MATRIX: dict[RiskBand, dict[ActionSensitivity, dict[str, Any]]] = {
    "low": {
        "low": {"action": "allow"},
        "medium": {"action": "allow"},
        "high": {"action": "verify", "assurance": "light", "cooling_off": True},
    },
    "medium": {
        "low": {"action": "allow"},
        "medium": {"action": "verify", "assurance": "light"},
        "high": {"action": "verify", "assurance": "strong", "reconfirm": True},
    },
    "high": {
        "low": {"action": "verify", "assurance": "light"},
        "medium": {"action": "verify", "assurance": "strong"},
        "high": {
            "action": "block",
            "assurance": "strong",
            "reconfirm": True,
            "cooling_off": True,
        },
    },
}

_DEFAULT_STAKES: ActionSensitivity = "medium"


class Decision(BaseModel):
    action: Action
    assurance: Assurance | None = None
    action_sensitivity: ActionSensitivity
    cooling_off: bool = False
    reconfirm: bool = False
    block_alert: bool = False


def _resolve_stakes(action_type: str, policy: Mapping[str, Any]) -> ActionSensitivity:
    entry = policy.get("action_sensitivity", {}).get(action_type, {})
    return entry.get("stakes", _DEFAULT_STAKES)


def decide(
    band: RiskBand,
    action_type: str,
    *,
    policy: Mapping[str, Any],
    cold_start: bool = False,
    degraded: bool = False,
) -> Decision:
    stakes = _resolve_stakes(action_type, policy)

    if band == "very_high":
        cell: dict[str, Any] = {"action": "block", "assurance": "strong", "block_alert": True}
    else:
        cell = dict(RISK_ACTION_MATRIX[band][stakes])

    # Cold-start: redistribute risk to context/IF-prior + rules, never block a brand-new
    # user purely for being new (CLAUDE.md invariant 9).
    if cold_start and cell["action"] == "block":
        cell = {**cell, "action": "verify", "assurance": "strong"}

    # Degraded scoring (XGBoost/Redis fallback): never silently allow on a score we
    # don't fully trust (CLAUDE.md invariant 10).
    if degraded and cell["action"] == "allow":
        cell = {**cell, "action": "verify", "assurance": "light"}

    return Decision(
        action=cell["action"],
        assurance=cell.get("assurance"),
        action_sensitivity=stakes,
        cooling_off=cell.get("cooling_off", False),
        reconfirm=cell.get("reconfirm", False),
        block_alert=cell.get("block_alert", False),
    )
