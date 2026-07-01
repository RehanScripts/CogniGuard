import json
import uuid

import pytest

from app import kafka_client
from app.schemas.topics import (
    BehaviorEvent,
    DecisionEvent,
    DeviceEvent,
    LoginEventMsg,
    RiskScoreEvent,
    TransactionEvent,
    T_TRANSACTION,
)
from app.services import event_producer as ep

# --- unit: build_* payloads validate against the topic schemas (no broker) ------


def test_build_login_event_validates():
    d = ep.build_login_event(session_id="s1", device_id="d1", ip="1.2.3.4", asn=64512)
    LoginEventMsg.model_validate(d)  # raises on mismatch
    assert d["ts"]  # ts auto-populated


def test_build_behavior_event_validates():
    d = ep.build_behavior_event(session_id="s1", typing_speed=4.2, typing_rhythm=[0.1, 0.2])
    BehaviorEvent.model_validate(d)
    assert d["typing_rhythm"] == [0.1, 0.2]


def test_build_device_event_validates():
    d = ep.build_device_event(device_fingerprint="fp", os="android", is_rooted=True)
    DeviceEvent.model_validate(d)
    assert d["is_rooted"] is True


def test_build_transaction_event_validates():
    d = ep.build_transaction_event(transaction_id="t1", amount=50000, is_new_payee=True)
    TransactionEvent.model_validate(d)
    assert d["amount"] == 50000


def test_build_risk_score_event_validates():
    d = ep.build_risk_score_event(
        entity_type="login",
        entity_id="s1",
        behavior_score=0.1,
        device_score=0.0,
        transaction_score=0.27,
        final_risk_score=27.0,
        risk_band="low",
        model_version="xgboost_txn@test",
    )
    RiskScoreEvent.model_validate(d)


def test_build_decision_event_validates():
    d = ep.build_decision_event(
        entity_type="transaction",
        entity_id="t1",
        action="verify",
        required_factors=["OTP"],
        reason_codes=[{"code": "NEW_BENEF_HIGHVAL", "detail": "x"}],
    )
    DecisionEvent.model_validate(d)
    assert d["action"] == "verify"


# --- integration: produce → consume round-trip (skips if Kafka unreachable) ------


@pytest.mark.skipif(not kafka_client.ping(), reason="Kafka broker not reachable")
def test_produce_consume_roundtrip():
    from scripts.create_topics import create_topics

    create_topics()
    marker = uuid.uuid4().hex
    user_id = "u-test"
    ep.emit_transaction_event(user_id=user_id, transaction_id=marker, amount=123.45)
    kafka_client.get_producer().flush(10)

    consumer = kafka_client.get_consumer(f"test-{marker}", [T_TRANSACTION])
    try:
        found = None
        for _ in range(100):  # poll up to ~20s to allow partition assignment + delivery
            msg = consumer.poll(0.2)
            if msg is None or msg.error():
                continue
            payload = json.loads(msg.value())
            if payload.get("transaction_id") == marker:
                found = payload
                break
        assert found is not None, "produced transaction_event not consumed back"
        assert found["amount"] == 123.45
    finally:
        consumer.close()
