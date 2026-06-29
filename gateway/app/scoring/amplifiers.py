"""§10.3 Dynamic Risk Amplifiers (multiplicative). Multipliers come ONLY from the active
policy -- never hardcoded (CLAUDE.md invariant 12).
"""

from __future__ import annotations

from typing import Mapping

from pydantic import BaseModel

from ..schemas.scoring import Amplifier


class TxnContext(BaseModel):
    """Minimal transaction-context contract evaluate() needs -- sourced by the caller
    (Phase 7/8) from whatever Redis/Postgres reads it already does; Phase 6 only defines
    the shape, no new Redis keys/Flink wiring."""

    payee_age_minutes: float | None = None  # None = not a freshly-added payee / unknown
    daily_avg_amount: float = 0.0
    amount: float = 0.0
    new_payee_count_recent: int = 0  # distinct new payees in the fan-out window
    account_balance: float | None = None
    odd_time: bool = False
    pre_txn_dwell_ms: float = 0.0


# Feature-engineering constants that decide whether a trigger condition is true at all
# (same category as feature_reader.py's ODD_TIME_HOURS) -- NOT the multiplier, which
# always comes from policy.
NEW_PAYEE_WINDOW_MIN = 120  # "<2h"
NEW_PAYEE_AMOUNT_RATIO = 0.80  # ">80% daily-avg"
RAPID_FANOUT_MIN_PAYEES = 3  # "≥N distinct new payees"
DRAIN_BALANCE_RATIO = 0.90  # "≥90% balance"
COERCION_DWELL_MS = 30_000  # "long pre-txn dwell"
AMOUNT_SPIKE_RATIO = 3.0  # fires when amount > 3× the 30-day daily average


def evaluate(txn_ctx: TxnContext, policy_amps: Mapping[str, float]) -> list[Amplifier]:
    fired: list[Amplifier] = []

    if (
        txn_ctx.payee_age_minutes is not None
        and txn_ctx.payee_age_minutes < NEW_PAYEE_WINDOW_MIN
        and txn_ctx.daily_avg_amount > 0
        and txn_ctx.amount > NEW_PAYEE_AMOUNT_RATIO * txn_ctx.daily_avg_amount
    ):
        fired.append(
            Amplifier(
                code="NEW_BENEF_HIGHVAL",
                multiplier=policy_amps["NEW_BENEF_HIGHVAL"],
                detail=f"payee added {txn_ctx.payee_age_minutes:.0f}min ago, amount exceeds 80% of daily avg",
            )
        )

    if (
        txn_ctx.daily_avg_amount > 0
        and txn_ctx.amount > AMOUNT_SPIKE_RATIO * txn_ctx.daily_avg_amount
    ):
        fired.append(
            Amplifier(
                code="AMOUNT_SPIKE",
                multiplier=policy_amps.get("AMOUNT_SPIKE", 1.4),
                detail=f"amount is {txn_ctx.amount / txn_ctx.daily_avg_amount:.1f}× the 30-day daily average",
            )
        )

    if txn_ctx.new_payee_count_recent >= RAPID_FANOUT_MIN_PAYEES:
        fired.append(
            Amplifier(
                code="RAPID_FANOUT",
                multiplier=policy_amps["RAPID_FANOUT"],
                detail=f"{txn_ctx.new_payee_count_recent} distinct new payees in window",
            )
        )

    if (
        txn_ctx.account_balance is not None
        and txn_ctx.account_balance > 0
        and txn_ctx.payee_age_minutes is not None
        and txn_ctx.payee_age_minutes < NEW_PAYEE_WINDOW_MIN
        and txn_ctx.amount >= DRAIN_BALANCE_RATIO * txn_ctx.account_balance
    ):
        fired.append(
            Amplifier(
                code="DRAIN",
                multiplier=policy_amps["DRAIN"],
                detail="transfer drains ≥90% of balance to a new payee",
            )
        )

    if txn_ctx.odd_time and txn_ctx.pre_txn_dwell_ms >= COERCION_DWELL_MS:
        fired.append(
            Amplifier(
                code="COERCION_TIME",
                multiplier=policy_amps["COERCION_TIME"],
                detail="odd-hour transaction after a long pre-transaction pause",
            )
        )

    return fired


def apply(base: float, fired: list[Amplifier]) -> float:
    product = 1.0
    for amp in fired:
        product *= amp.multiplier
    return max(0.0, min(100.0, base * product))
