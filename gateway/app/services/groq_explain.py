"""Groq-powered analyst narrative for SHAP explanations (off hot path, analyst-triggered).

Called from shap_explainer.explain_score() after SHAP values and full scoring context
are assembled.  Falls back to None gracefully when GROQ_API_KEY is absent or the API
is unreachable — the plain SHAP bar chart remains as the fallback (CLAUDE.md invariant
16: deterministic reason codes on the hot path; Groq runs off-path, analyst-only).

Context dict keys (all optional, best-effort from DB joins):
  entity_type       "login" | "transaction"
  risk_score        float 0-100
  risk_band         "low" | "medium" | "high" | "very_high"
  action            "allow" | "verify" | "block"
  reason_codes      list[str]  — e.g. ["NEW_DEVICE", "GEO_CHANGE"]
  amplifiers        list[str]  — e.g. ["NEW_BENEF_HIGHVAL", "DRAIN"]
  required_factors  list[str]  — e.g. ["OTP", "FINGERPRINT"]
  behavior_score    float | None
  device_score      float | None
  trust_score       float | None
  behavior_match    float | None
  behavior_score_source  "ae" | "if" | "fallback" | None
  amount            float | None   (transaction only)
  transfer_type     str | None     ("IMPS"|"NEFT"|"RTGS"|"UPI")
  channel           str | None     ("web"|"mobile")
  is_new_payee      bool | None
  geo_city          str | None
  geo_country       str | None
  is_vpn            bool
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from ..config import settings

logger = logging.getLogger(__name__)

_SRC_LABEL = {"ae": "LSTM-AE", "if": "Isolation-Forest", "fallback": "fallback"}


def generate_shap_explanation(top_features: list[dict], ctx: dict) -> str | None:
    """Return a 3-4 sentence analyst-friendly narrative, or None on missing key / API error."""
    if not settings.groq_api_key:
        return None

    prompt = _build_prompt(top_features, ctx)
    payload = json.dumps(
        {
            "model": settings.groq_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 700,
            "temperature": 0.3,
        }
    ).encode()

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {settings.groq_api_key}",
            "Content-Type": "application/json",
            # Cloudflare WAF blocks raw urllib requests from Docker containers (1010 error).
            # A browser-like User-Agent routes the request through the normal path.
            "User-Agent": "Mozilla/5.0 (compatible; CogniGuard-SOC/1.0)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data["choices"][0]["message"]["content"].strip()
    except Exception:
        logger.warning("Groq explain unavailable — returning SHAP only")
        return None


def _build_prompt(top_features: list[dict], ctx: dict) -> str:
    entity = (ctx.get("entity_type") or "event").upper()
    score = ctx.get("risk_score", 0.0)
    band = (ctx.get("risk_band") or "unknown").replace("_", " ").upper()
    action = (ctx.get("action") or "unknown").upper()

    lines: list[str] = [
        f"FRAUD ANALYST BRIEFING — {entity}",
        f"Decision: {action}  |  Risk: {score:.0f}/100  |  Band: {band}",
        "",
    ]

    # Behavioral / identity signal summary
    sig: list[str] = []
    bss = ctx.get("behavior_score_source") or ""
    src = _SRC_LABEL.get(bss, bss)
    if ctx.get("behavior_score") is not None:
        sig.append(f"behavioral anomaly {ctx['behavior_score']:.2f}/1.0 ({src})")
    if ctx.get("device_score") is not None:
        sig.append(f"device trust {ctx['device_score']:.2f}/1.0")
    if ctx.get("trust_score") is not None:
        sig.append(f"identity trust {ctx['trust_score']:.2f}/1.0")
    if ctx.get("behavior_match") is not None:
        sig.append(f"behavior-match {ctx['behavior_match']:.2f}/1.0")
    if sig:
        lines.append("Signals: " + " | ".join(sig))

    # Reason codes
    rc: list[str] = ctx.get("reason_codes") or []
    if rc:
        lines.append("Reason codes fired: " + ", ".join(rc))

    # Amplifiers
    amps: list[str] = ctx.get("amplifiers") or []
    if amps:
        lines.append("Risk amplifiers: " + ", ".join(amps))

    # Transaction-specific context
    if ctx.get("entity_type") == "transaction":
        txn_parts: list[str] = []
        if ctx.get("amount") is not None:
            txn_parts.append(f"₹{ctx['amount']:,.0f}")
        if ctx.get("transfer_type"):
            txn_parts.append(str(ctx["transfer_type"]))
        if ctx.get("channel"):
            txn_parts.append(f"via {ctx['channel']}")
        if ctx.get("is_new_payee"):
            txn_parts.append("NEW PAYEE (added recently)")
        if txn_parts:
            lines.append("Transaction: " + " | ".join(txn_parts))

    # Geo / device context
    geo_parts: list[str] = []
    location = ", ".join(p for p in [ctx.get("geo_city"), ctx.get("geo_country")] if p)
    if location:
        geo_parts.append(f"session from {location}")
    if ctx.get("is_vpn"):
        geo_parts.append("VPN detected")
    if geo_parts:
        lines.append("Device/geo: " + " | ".join(geo_parts))

    # Step-up factors ordered
    factors: list = ctx.get("required_factors") or []
    if factors:
        lines.append("Step-up required: " + ", ".join(str(f) for f in factors))

    # Top SHAP features (model explainability)
    shap_lines = [
        f"  • {f['feature']}: {f['shap_value']:+.3f}"
        + (f" (actual={f['feature_value']:.3f})" if f.get("feature_value") is not None else "")
        for f in top_features[:5]
    ]
    if shap_lines:
        lines.append(
            "Top SHAP model drivers (+ = increases fraud probability, − = decreases it):\n"
            + "\n".join(shap_lines)
        )

    briefing = "\n".join(lines)
    return (
        briefing
        + "\n\n"
        + "Write a structured analyst-grade explanation in markdown using this exact format:\n\n"
        + "**Verdict:** One sentence stating the decision and the single most important reason.\n\n"
        + "**Why flagged:**\n"
        + "- **SIGNAL_NAME** — plain-English meaning of this signal (no raw numbers, no jargon).\n"
        + "- **SIGNAL_NAME** — (repeat for each fired reason code, amplifier, or top SHAP driver — up to 5)\n\n"
        + "**What it means:** One sentence explaining what this pattern of signals suggests about the user's intent or account state.\n\n"
        + "**Recommended action:** One concrete step the analyst should take right now.\n\n"
        + "Rules: Use **BOLD** for every signal/reason-code name. Reference the actual data above. "
        + "Translate numbers into meaning — do not repeat raw values. Keep each bullet under 20 words."
    )
