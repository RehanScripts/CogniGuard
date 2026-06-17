"""Transaction-fraud layer controls (Implementation.md Phase 7, PRD §10.3): Cooling
Period, Reconfirmation, Manual Amount Entry, Coercion Check. Fired when the
transaction risk score exceeds the threshold (`band` is high/very_high) **or** an
amplifier fires -- this is what catches "genuine behavior, dangerous intent" on a
clean-looking medium-band transaction that only became risky because of who/how much/
when it's being sent to.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Mapping

from ..schemas.decision import TxnControls
from ..schemas.scoring import Amplifier, RiskBand
from ..scoring.amplifiers import TxnContext

# Which controls each amplifier forces on, independent of band.
AMPLIFIER_CONTROLS: dict[str, dict[str, bool]] = {
    "NEW_BENEF_HIGHVAL": {"cooling": True, "manual_amount": True},
    "RAPID_FANOUT": {"reconfirm": True, "manual_amount": True},
    "DRAIN": {"cooling": True, "reconfirm": True, "manual_amount": True},
    "COERCION_TIME": {"coercion_check": True, "manual_amount": True},
}

_HIGH_RISK_BANDS = ("high", "very_high")


def resolve_controls(
    band: RiskBand,
    amps: list[Amplifier],
    txn_ctx: TxnContext,
    policy: Mapping[str, Any],
) -> TxnControls:
    triggered = band in _HIGH_RISK_BANDS or bool(amps)
    if not triggered:
        return TxnControls()

    cooling = False
    reconfirm = False
    manual_amount = False
    coercion_check = False

    for amp in amps:
        controls = AMPLIFIER_CONTROLS.get(amp.code, {})
        cooling = cooling or controls.get("cooling", False)
        reconfirm = reconfirm or controls.get("reconfirm", False)
        manual_amount = manual_amount or controls.get("manual_amount", False)
        coercion_check = coercion_check or controls.get("coercion_check", False)

    # A high/very_high transaction always gets full scrutiny, not just whatever a
    # specific amplifier happened to fire.
    if band in _HIGH_RISK_BANDS:
        reconfirm = True
        manual_amount = True
        coercion_check = True

    cooling_off_policy = policy.get("cooling_off", {})
    cooling_until = None
    if cooling:
        minutes = cooling_off_policy.get("minutes", 30)
        cooling_until = (
            dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes)
        ).isoformat()

    reconfirm_channel = None
    if reconfirm:
        reconfirm_channel = cooling_off_policy.get("reconfirm_channel", "APP_PUSH")

    return TxnControls(
        cooling_until=cooling_until,
        manual_amount=manual_amount,
        coercion_check=coercion_check,
        reconfirm=reconfirm_channel,
    )
