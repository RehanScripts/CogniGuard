import json
import pathlib

import pytest
from pydantic import ValidationError

from app.schemas.behavior import BehaviorPayload
from app.schemas.decision import DecisionResponse
from app.schemas.features import FeatureBundle
from app.schemas.payment import PaymentScoreRequest, PaymentScoreResponse
from app.schemas.scoring import Amplifier, ScoreResult

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _genuine() -> dict:
    return json.loads((FIXTURES / "payload_genuine.json").read_text())


def test_behavior_payload_validates_web_fixture():
    p = BehaviorPayload.model_validate(_genuine())
    assert p.channel == "web"
    assert p.source == "web_sdk"
    assert p.keystroke is not None and len(p.keystroke.events) == 3
    assert p.derived_features is None  # web path uses raw blocks


def test_behavior_payload_mobile_derived_features():
    raw = _genuine()
    raw["channel"] = "mobile"
    raw["source"] = "mobile_edge"
    raw.pop("keystroke")
    raw.pop("mouse")
    raw["derived_features"] = {"swipe_velocity_norm": 1.4, "touch_pressure_avg": 0.5}
    p = BehaviorPayload.model_validate(raw)
    assert p.channel == "mobile"
    assert p.keystroke is None
    assert p.derived_features["swipe_velocity_norm"] == 1.4


def test_behavior_payload_rejects_bad_channel():
    raw = _genuine()
    raw["channel"] = "atm"
    with pytest.raises(ValidationError):
        BehaviorPayload.model_validate(raw)


def test_behavior_payload_requires_integrity_fields():
    raw = _genuine()
    raw.pop("nonce")
    with pytest.raises(ValidationError):
        BehaviorPayload.model_validate(raw)


def test_decision_response_defaults():
    d = DecisionResponse(action="allow", entity_type="login", risk_score=27.0, risk_band="low")
    assert d.integrity == "OK"
    assert d.required_factors == []
    assert d.step_up is None


def test_amplifier_as_reason_roundtrip():
    a = Amplifier(code="NEW_BENEF_HIGHVAL", multiplier=1.5, detail="new payee + high value")
    rc = a.as_reason()
    assert rc.code == "NEW_BENEF_HIGHVAL"
    assert "high value" in rc.detail


def test_score_result_band_literal():
    s = ScoreResult(
        behavior_score=0.1,
        transaction_score=0.27,
        final_risk_score=27.0,
        risk_band="low",
        model_version="xgboost_txn@test",
    )
    assert s.risk_band == "low"


def test_payment_response_is_decision_with_base_score():
    req = PaymentScoreRequest(amount=50000, beneficiary_vpa="scammer@upi", behavior=_genuine())
    assert req.transfer_type == "UPI"
    resp = PaymentScoreResponse(
        action="verify", entity_type="transaction", risk_score=37.5, risk_band="medium", base_score=25.0
    )
    assert resp.base_score == 25.0
    assert resp.entity_type == "transaction"


# --- Phase 14: additive AE fields default to unset / don't disturb existing contracts -


def test_behavior_payload_ae_fields_default_to_none_and_round_trip():
    p = BehaviorPayload.model_validate(_genuine())
    assert p.ae_recon_error is None
    assert p.ae_model_version is None

    raw = _genuine()
    raw["ae_recon_error"] = 0.37
    raw["ae_model_version"] = "lstm_autoencoder_tflite@2026-06-01"
    mobile = BehaviorPayload.model_validate(raw)
    assert mobile.ae_recon_error == 0.37
    assert mobile.ae_model_version == "lstm_autoencoder_tflite@2026-06-01"


def test_score_result_ae_provenance_fields_default_to_none():
    s = ScoreResult(
        behavior_score=0.1,
        transaction_score=0.27,
        final_risk_score=27.0,
        risk_band="low",
        model_version="xgboost_txn@test",
    )
    assert s.behavior_score_source is None
    assert s.if_shadow_score is None
    assert s.ae_recon_error is None

    s2 = ScoreResult(
        behavior_score=0.1,
        transaction_score=0.27,
        final_risk_score=27.0,
        risk_band="low",
        model_version="xgboost_txn@test",
        behavior_score_source="ae",
        if_shadow_score=0.2,
        ae_recon_error=0.05,
    )
    assert s2.behavior_score_source == "ae"
    assert s2.if_shadow_score == 0.2
    assert s2.ae_recon_error == 0.05


def test_feature_bundle_ae_fields_default_safely():
    bundle = FeatureBundle(user_id="u1")
    assert bundle.behavior_sequence is None
    assert bundle.behavior_sequence_mask is None
    assert bundle.ae_recon_error is None
    assert bundle.ae_cold_start is False  # caller (feature_reader) sets this explicitly

    bundle2 = FeatureBundle(
        user_id="u1",
        behavior_sequence=[[0.0] * 9, [1.0] * 9],
        behavior_sequence_mask=[False, True],
        ae_cold_start=True,
    )
    assert bundle2.behavior_sequence == [[0.0] * 9, [1.0] * 9]
    assert bundle2.ae_cold_start is True
