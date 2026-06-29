"""LLM investigation assistant (Phase D5).

Provider interface + deterministic local stub now; Claude API deferred until
ANTHROPIC_API_KEY + LLM_PROVIDER=claude are set in env.

Usage:
    provider = get_provider()
    result = await provider.investigate(case_id, context)
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..config import settings
from ..models.governance import Case
from ..models.scoring import Decision, RiskScore
from ..models.transaction import Transaction
from ..schemas.admin import InvestigationResultOut

logger = logging.getLogger(__name__)


class InvestigationProvider(Protocol):
    async def investigate(
        self, case_id: str, case: Case, db: DbSession
    ) -> InvestigationResultOut: ...


class DeterministicStubProvider:
    """Builds a structured investigation summary from existing DB data without any LLM."""

    async def investigate(
        self, case_id: str, case: Case, db: DbSession
    ) -> InvestigationResultOut:
        risk_factors: list[str] = []
        summary_parts: list[str] = []

        summary_parts.append(
            f"Case {case_id[:8]}… opened {_fmt(case.created_at)}. "
            f"Status: {case.status}. Severity: {case.severity or 'unknown'}."
        )

        transaction: Transaction | None = None
        if case.transaction_id:
            transaction = db.get(Transaction, case.transaction_id)

        if transaction:
            summary_parts.append(
                f"Linked transaction: {transaction.transfer_type} of "
                f"₹{float(transaction.amount or 0):,.0f} "
                f"({transaction.status}). "
                f"{'New beneficiary.' if transaction.is_new_payee else 'Known beneficiary.'}"
            )
            if transaction.is_new_payee:
                risk_factors.append("Transfer to a new/unverified beneficiary")
            if transaction.amount and float(transaction.amount) >= 50_000:
                risk_factors.append(f"High-value transfer (₹{float(transaction.amount):,.0f})")

        risk_score = None
        if case.transaction_id:
            risk_score = db.scalar(
                select(RiskScore)
                .where(RiskScore.entity_id == case.transaction_id)
                .order_by(RiskScore.scored_at.desc())
            )
        elif case.user_id:
            risk_score = db.scalar(
                select(RiskScore)
                .where(RiskScore.user_id == case.user_id)
                .order_by(RiskScore.scored_at.desc())
            )

        decision_action: str | None = None
        if risk_score:
            band = risk_score.risk_band or "unknown"
            score = float(risk_score.final_risk_score or 0)
            source = risk_score.behavior_score_source or "unknown"
            summary_parts.append(
                f"Risk score: {score:.1f} ({band} band). "
                f"Behavior source: {source}. "
                f"Model: {risk_score.model_version or 'unknown'}."
            )
            if band in ("high", "very_high"):
                risk_factors.append(f"Risk band is '{band}' (score {score:.1f})")
            decision_row = db.scalar(
                select(Decision).where(Decision.entity_id == risk_score.entity_id)
            )
            if decision_row:
                decision_action = decision_row.action
                reason_codes = decision_row.reason_codes or []
                if reason_codes:
                    codes = ", ".join(
                        r.get("code", str(r)) for r in (reason_codes if isinstance(reason_codes, list) else [])
                    )
                    risk_factors.append(f"Decision reason codes: {codes}")

        recommendation = _recommend(decision_action, risk_factors)

        return InvestigationResultOut(
            case_id=case_id,
            provider="stub",
            summary=" ".join(summary_parts),
            risk_factors=risk_factors,
            recommendation=recommendation,
            generated_at=dt.datetime.now(dt.timezone.utc),
        )


class ClaudeProvider:
    """Calls Anthropic Messages API.  Activated by LLM_PROVIDER=claude + ANTHROPIC_API_KEY."""

    async def investigate(
        self, case_id: str, case: Case, db: DbSession
    ) -> InvestigationResultOut:
        try:
            import anthropic  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError("anthropic package is not installed") from exc

        stub = DeterministicStubProvider()
        stub_result = await stub.investigate(case_id, case, db)

        prompt = (
            f"You are a fraud analyst at Central Bank of India reviewing a flagged case.\n\n"
            f"Case summary: {stub_result.summary}\n"
            f"Risk factors: {json.dumps(stub_result.risk_factors)}\n\n"
            "In 2-3 sentences: (1) What is the most likely fraud scenario? "
            "(2) What additional verification would you request from the customer? "
            "(3) Should this case be escalated or can it be resolved with a step-up? "
            "Be concise and actionable."
        )

        client = anthropic.AsyncAnthropic(api_key=getattr(settings, "anthropic_api_key", ""))
        message = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        llm_text = message.content[0].text if message.content else ""

        return InvestigationResultOut(
            case_id=case_id,
            provider="claude",
            summary=stub_result.summary + " [LLM analysis below]",
            risk_factors=stub_result.risk_factors,
            recommendation=llm_text,
            generated_at=dt.datetime.now(dt.timezone.utc),
        )


def get_provider() -> InvestigationProvider:
    llm_provider = getattr(settings, "llm_provider", "stub")
    if llm_provider == "claude":
        return ClaudeProvider()
    return DeterministicStubProvider()


def _fmt(dt_val: dt.datetime | None) -> str:
    return dt_val.strftime("%Y-%m-%d %H:%M UTC") if dt_val else "unknown time"


def _recommend(action: str | None, risk_factors: list[str]) -> str:
    if not risk_factors:
        return "No significant risk factors detected. Consider closing as false positive after review."
    if action == "block":
        return (
            "Transaction was blocked due to high risk. Recommend confirming with the customer "
            "via a registered phone call before any reversal. Escalate if customer reports coercion."
        )
    if action == "verify":
        return (
            "Step-up authentication was triggered. Verify that the customer initiated this transaction "
            "willingly. If any coercion indicator is present, escalate to the fraud team immediately."
        )
    return (
        "Review the listed risk factors with the customer. Request out-of-band confirmation "
        "if the transaction amount is unusually large or the beneficiary is new."
    )
