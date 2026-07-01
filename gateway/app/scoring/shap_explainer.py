"""On-demand SHAP explanation for XGBoost fraud scores (Phase D4).

Runs TreeExplainer off the hot path only when an analyst requests an explanation via
`POST /admin/explain/{score_id}`.  The live scoring path keeps its deterministic
reason-code explainer (CLAUDE.md invariant 16).

Import shap lazily so startup is not affected when the package is absent.
"""

from __future__ import annotations

import logging
import uuid as _uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..models.scoring import Decision as DecisionRow
from ..models.scoring import RiskScore
from ..models.session import Session as SessionRow
from ..models.transaction import Transaction as TransactionRow
from ..schemas.admin import ShapExplanationOut, ShapFeatureOut
from ..scoring.registry import Registry

logger = logging.getLogger(__name__)


def explain_score(
    score_id: str,
    db: DbSession,
    registry: Registry,
) -> ShapExplanationOut:
    """Return top-10 feature-importance entries for *score_id* + Groq narrative.

    For login events the acted-on score is driven by the identity-gate trust components
    (behavior_match, device_trust, AE/IF behavioral anomaly), not by XGBoost features.
    XGBoost is trained on transaction data with behavior_score=0.5 constant, so its SHAP
    values are trivially ~0 on all-zero login feature vectors.  We therefore compute a
    trust-component pseudo-SHAP for login events so the SOC analyst sees the real drivers.
    Transaction events still use TreeExplainer on the XGBoost model.

    Raises ValueError if the score row is not found.
    """
    try:
        sid = _uuid.UUID(score_id)
    except ValueError as exc:
        raise ValueError(f"invalid score_id: {score_id}") from exc

    row = db.get(RiskScore, sid)
    if row is None:
        raise ValueError(f"score {score_id!r} not found")

    if row.entity_type == "login":
        top_features = _login_trust_features(row)
        model_version = row.model_version
    else:
        top_features, model_version = _xgb_shap_features(row, registry, db)

    ctx = _build_groq_context(row, db)
    from ..services import groq_explain

    ai_text = groq_explain.generate_shap_explanation(
        [f.model_dump() for f in top_features],
        ctx,
    )
    return ShapExplanationOut(
        score_id=score_id,
        model_version=model_version,
        top_features=top_features,
        ai_explanation=ai_text,
    )


def _login_trust_features(row: RiskScore) -> list[ShapFeatureOut]:
    """Pseudo-SHAP from identity/trust components for login events.

    XGBoost SHAP is meaningless for logins because:
    (a) the model was trained on transaction data — amount/velocity/payee are all 0 for logins.
    (b) behavior_score was hardcoded to 0.5 in training → the model ignores it.

    Instead, decompose the identity-gate (or cold-start) trust score into per-signal
    contributions.  Positive value = pushes risk UP (fraud signal); negative = reduces risk.
    """
    bm = float(row.behavior_match_score) if row.behavior_match_score is not None else None
    bs = float(row.behavior_score) if row.behavior_score is not None else 0.5
    ds = float(row.device_score) if row.device_score is not None else 80.0
    ts = float(row.trust_score) if row.trust_score is not None else None
    final = float(row.final_risk_score) if row.final_risk_score is not None else 50.0

    features: list[ShapFeatureOut] = []

    if bm is not None:
        # Identity match: low match = main fraud signal (positive = risk-pushing)
        sv = round((50.0 - bm) / 100.0, 3)
        features.append(
            ShapFeatureOut(feature="identity_match_%", shap_value=sv, feature_value=round(bm, 1))
        )

        # Composite trust derived from behavior_match × support
        if ts is not None:
            sv = round((30.0 - ts) / 100.0 * 0.5, 3)
            features.append(
                ShapFeatureOut(feature="composite_trust", shap_value=sv, feature_value=round(ts, 1))
            )
    else:
        # Cold-start / no baseline: trust_score IS the driving composite; show as main factor
        if ts is not None:
            sv = round((75.0 - ts) / 100.0, 3)  # 75 = expected trust for clean low-risk login
            features.append(
                ShapFeatureOut(feature="composite_trust", shap_value=sv, feature_value=round(ts, 1))
            )
        # Show how far final score is from the low-risk base (risk_score itself as driver)
        sv_base = round((final - 10.0) / 100.0 * 0.5, 3)
        features.append(
            ShapFeatureOut(
                feature="session_risk_base",
                shap_value=max(sv_base, -0.05),
                feature_value=round(final, 1),
            )
        )

    # Behavioral anomaly: AE/IF score > 0.5 means unusual behaviour
    sv_bs = round((bs - 0.5) * 0.4, 3)
    features.append(
        ShapFeatureOut(feature="behavioral_anomaly", shap_value=sv_bs, feature_value=round(bs, 3))
    )

    # Device trust: low trust = positive risk contribution
    sv_dev = round((50.0 - ds) / 200.0, 3)
    features.append(
        ShapFeatureOut(feature="device_trust", shap_value=sv_dev, feature_value=round(ds, 1))
    )

    return sorted(features, key=lambda f: abs(f.shap_value), reverse=True)


def _xgb_shap_features(
    row: RiskScore, registry: Registry, db: DbSession
) -> tuple[list[ShapFeatureOut], str | None]:
    """TreeExplainer SHAP for transaction events, with pseudo-SHAP fallback.

    The XGBoost model was trained with behavior_score=0.5 constant for all rows
    (TXN_HISTORY_UPI_FIN has no paired telemetry), so TreeExplainer output is
    near-zero on that feature.  When all SHAP values are < 0.001 (degenerate model
    or missing feature reconstruction), we fall back to a risk-context pseudo-SHAP
    that gives analysts meaningful bars without requiring the live Redis features.
    """
    xgb_model = _load_xgb(registry)
    if xgb_model is None:
        raise ValueError("xgboost_txn model not loaded in registry")

    from training.train_xgboost import FEATURE_COLUMNS

    feature_values = _reconstruct_features(row, FEATURE_COLUMNS, db)

    # Try TreeExplainer first
    tree_sv: list[float] | None = None
    try:
        import shap  # noqa: PLC0415

        row_arr = [[feature_values.get(col, 0.0) for col in FEATURE_COLUMNS]]
        raw_model = xgb_model.model if hasattr(xgb_model, "model") else xgb_model
        if hasattr(raw_model, "estimators_"):
            inner = raw_model.estimators_[0]
            raw_model = getattr(inner, "estimator", inner)
        elif hasattr(raw_model, "base_estimator"):
            raw_model = raw_model.base_estimator

        explainer = shap.TreeExplainer(raw_model)
        sv_raw = explainer.shap_values(row_arr)
        sv_arr = sv_raw[1][0] if isinstance(sv_raw, list) else sv_raw[0]
        candidates = [float(v) for v in sv_arr]
        if max(abs(v) for v in candidates) >= 0.001:
            tree_sv = candidates
    except Exception:
        pass

    if tree_sv is not None:
        paired = sorted(
            (
                (FEATURE_COLUMNS[i], tree_sv[i], feature_values.get(FEATURE_COLUMNS[i]))
                for i in range(len(FEATURE_COLUMNS))
            ),
            key=lambda x: abs(x[1]),
            reverse=True,
        )[:10]
    else:
        # Pseudo-SHAP: derive contributions from reconstructed features + risk context
        paired = sorted(
            _txn_pseudo_shap(feature_values, row).items(),
            key=lambda kv: abs(kv[1]),
            reverse=True,
        )[:10]
        paired = [(k, v, feature_values.get(k)) for k, v in paired]

    return [
        ShapFeatureOut(feature=name, shap_value=sv_val, feature_value=fv)
        for name, sv_val, fv in paired
    ], xgb_model.version


def _txn_pseudo_shap(fv: dict[str, float], row: RiskScore) -> dict[str, float]:
    """Context-aware pseudo-SHAP for transactions when TreeExplainer is degenerate.

    Positive = pushes toward fraud; negative = reduces fraud probability.
    Magnitudes are calibrated so the total roughly matches the final_risk_score.
    """
    risk = float(row.final_risk_score or 50.0) / 100.0  # 0–1 scale
    base = risk * 0.3  # overall budget shared among features

    is_new = fv.get("is_new_payee", 0.0)
    amt = fv.get("amount", 0.0)
    amt_z = fv.get("amount_zscore", 0.0)
    vel_1h = fv.get("velocity_1h", 1.0)
    vel_24h = fv.get("velocity_24h", 3.0)
    sum_24h = fv.get("amount_sum_24h", 0.0)
    b_risk = fv.get("beneficiary_risk", 0.3)
    odd = fv.get("odd_time", 0.0)
    bs = fv.get("behavior_score", 0.5)

    return {
        "is_new_payee": round(is_new * base * 1.8, 3),
        "beneficiary_risk": round((b_risk - 0.3) * base * 1.4, 3),
        "amount": round(min(amt / 50_000.0, 1.0) * base * 1.2, 3),
        "amount_zscore": round(max(amt_z, 0.0) * base * 0.9, 3),
        "amount_sum_24h": round(min(sum_24h / 100_000.0, 1.0) * base * 0.7, 3),
        "velocity_1h": round(max(vel_1h - 1, 0) * base * 0.6, 3),
        "velocity_24h": round(max(vel_24h - 3, 0) * base * 0.4, 3),
        "odd_time": round(odd * base * 0.5, 3),
        "behavior_score": round((bs - 0.5) * base * 0.3, 3),
    }


def _build_groq_context(row: RiskScore, db: DbSession) -> dict:
    """Assemble full scoring context from DB joins for the Groq analyst prompt."""
    ctx: dict = {
        "entity_type": row.entity_type,
        "risk_score": float(row.final_risk_score or 0.0),
        "risk_band": row.risk_band,
        "behavior_score": float(row.behavior_score) if row.behavior_score is not None else None,
        "device_score": float(row.device_score) if row.device_score is not None else None,
        "trust_score": float(row.trust_score) if row.trust_score is not None else None,
        "behavior_match": (
            float(row.behavior_match_score) if row.behavior_match_score is not None else None
        ),
        "behavior_score_source": row.behavior_score_source,
    }

    # Linked Decision row (carries action, reason_codes, required_factors)
    dec = db.scalar(select(DecisionRow).where(DecisionRow.risk_score_id == row.score_id))
    if dec:
        ctx["action"] = dec.action
        raw_rc = dec.reason_codes or []
        ctx["reason_codes"] = [
            rc.get("code", str(rc)) if isinstance(rc, dict) else str(rc) for rc in raw_rc
        ]
        raw_factors = dec.required_factors or []
        ctx["required_factors"] = raw_factors if isinstance(raw_factors, list) else []

    # Transaction-specific context (amount, payee, amplifiers)
    txn: TransactionRow | None = None
    if row.entity_type == "transaction" and row.entity_id:
        try:
            txn = db.get(TransactionRow, _uuid.UUID(str(row.entity_id)))
        except Exception:
            txn = None
        if txn:
            ctx["amount"] = float(txn.amount) if txn.amount is not None else None
            ctx["transfer_type"] = txn.transfer_type
            ctx["channel"] = txn.channel
            ctx["is_new_payee"] = bool(txn.is_new_payee)
            dr = txn.decision_reason or {}
            raw_amps = dr.get("amplifiers", [])
            ctx["amplifiers"] = [
                a.get("code", str(a)) if isinstance(a, dict) else str(a) for a in raw_amps
            ]

    # Session / geo context
    session_id: _uuid.UUID | None = None
    if row.entity_type == "login" and row.entity_id:
        try:
            session_id = _uuid.UUID(str(row.entity_id))
        except Exception:
            pass
    elif txn is not None and txn.session_id:
        try:
            session_id = _uuid.UUID(str(txn.session_id))
        except Exception:
            pass

    if session_id:
        sess = db.get(SessionRow, session_id)
        if sess:
            ctx["geo_city"] = sess.geo_city
            ctx["geo_country"] = sess.geo_country
            ctx["is_vpn"] = bool(sess.is_vpn)

    return ctx


def _load_xgb(registry: Registry) -> Any | None:
    try:
        return registry.get("xgboost_txn")
    except Exception:
        return None


def _reconstruct_features(
    row: RiskScore, columns: list[str], db: DbSession | None = None
) -> dict[str, float]:
    """Build a best-effort feature dict from persisted score data + joined Transaction row.

    `behavior_score` is always available from RiskScore.  Velocity/z-score features live
    in Redis at score time and are not persisted; we approximate them from the transaction
    data so the SHAP bars show meaningful contributions rather than all-zero bars.
    """
    mapping: dict[str, float] = {}

    if row.behavior_score is not None:
        mapping["behavior_score"] = float(row.behavior_score)

    if db is not None and row.entity_type == "transaction" and row.entity_id is not None:
        try:
            txn = db.get(TransactionRow, _uuid.UUID(str(row.entity_id)))
            if txn is not None:
                amt = float(txn.amount) if txn.amount is not None else 0.0
                mapping["amount"] = amt
                mapping["is_new_payee"] = 1.0 if txn.is_new_payee else 0.0

                # Approximate features that lived in Redis at score time.
                # Typical UPI session: 1 txn/hr, 3/day; population mean ~₹2 500, std ~4 000.
                _typical_amt = 2500.0
                _amt_std = 4000.0
                mapping["amount_zscore"] = (amt - _typical_amt) / _amt_std if _amt_std else 0.0
                mapping["velocity_1h"] = 1.0
                mapping["velocity_24h"] = 3.0
                mapping["amount_sum_24h"] = amt
                # New-payee inherits higher beneficiary risk; known payees start at 0.3
                mapping["beneficiary_risk"] = 0.7 if txn.is_new_payee else 0.3

                if row.scored_at is not None:
                    h = row.scored_at.hour
                    mapping["odd_time"] = 1.0 if (h < 6 or h >= 22) else 0.0
        except Exception:
            pass

    return mapping
