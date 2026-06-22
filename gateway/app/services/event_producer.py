"""Kafka event production (Architecture §4.2 / §6).

The gateway produces input events on every request so the Flink feature engine has a
stream, and emits the risk_scores / decisions output topics for the dashboard. All
production is fire-and-forget (≤5 ms enqueue budget) and must never block the hot path.

Each `build_*` returns a schema-validated dict (unit-testable without a broker); each
`emit_*` builds and produces.
"""

import datetime as dt

from .. import kafka_client
from ..schemas.topics import (
    T_BEHAVIOR,
    T_DECISIONS,
    T_DEVICE,
    T_LOGIN,
    T_RISK_SCORES,
    T_TRANSACTION,
    BehaviorEvent,
    DecisionEvent,
    DeviceEvent,
    LoginEventMsg,
    RiskScoreEvent,
    TransactionEvent,
)


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


# --- input topics ---------------------------------------------------------------


def build_login_event(
    *,
    user_id: str = "",
    session_id: str,
    device_id: str,
    ip: str = "",
    asn: int | None = None,
    is_vpn: bool = False,
    geo_lat: float | None = None,
    geo_lon: float | None = None,
    ts: str | None = None,
) -> dict:
    return LoginEventMsg(
        user_id=user_id,
        session_id=session_id,
        device_id=device_id,
        ip=ip,
        asn=asn,
        is_vpn=is_vpn,
        geo_lat=geo_lat,
        geo_lon=geo_lon,
        ts=ts or _now_iso(),
    ).model_dump()


def emit_login_event(*, user_id: str, **kwargs) -> None:
    kafka_client.produce(T_LOGIN, key=user_id, value=build_login_event(user_id=user_id, **kwargs))


def build_behavior_event(
    *,
    user_id: str = "",
    session_id: str,
    typing_speed: float = 0.0,
    typing_rhythm: list[float] | None = None,
    key_latency: float = 0.0,
    swipe_angle: float = 0.0,
    touch_pressure: float = 0.0,
    mouse_velocity: float = 0.0,
    ts: str | None = None,
) -> dict:
    return BehaviorEvent(
        user_id=user_id,
        session_id=session_id,
        typing_speed=typing_speed,
        typing_rhythm=typing_rhythm or [],
        key_latency=key_latency,
        swipe_angle=swipe_angle,
        touch_pressure=touch_pressure,
        mouse_velocity=mouse_velocity,
        ts=ts or _now_iso(),
    ).model_dump()


def emit_behavior_event(*, user_id: str, **kwargs) -> None:
    kafka_client.produce(
        T_BEHAVIOR, key=user_id, value=build_behavior_event(user_id=user_id, **kwargs)
    )


def build_device_event(
    *,
    device_id: str = "",
    device_fingerprint: str,
    os: str = "",
    app_version: str = "",
    is_rooted: bool = False,
    is_emulator: bool = False,
    ts: str | None = None,
) -> dict:
    return DeviceEvent(
        device_id=device_id,
        device_fingerprint=device_fingerprint,
        os=os,
        app_version=app_version,
        is_rooted=is_rooted,
        is_emulator=is_emulator,
        ts=ts or _now_iso(),
    ).model_dump()


def emit_device_event(*, device_id: str, **kwargs) -> None:
    kafka_client.produce(
        T_DEVICE, key=device_id, value=build_device_event(device_id=device_id, **kwargs)
    )


def build_transaction_event(
    *,
    user_id: str = "",
    transaction_id: str,
    amount: float,
    beneficiary_id: str | None = None,
    transfer_type: str = "UPI",
    is_new_payee: bool = False,
    ts: str | None = None,
) -> dict:
    return TransactionEvent(
        user_id=user_id,
        transaction_id=transaction_id,
        amount=amount,
        beneficiary_id=beneficiary_id,
        transfer_type=transfer_type,
        is_new_payee=is_new_payee,
        ts=ts or _now_iso(),
    ).model_dump()


def emit_transaction_event(*, user_id: str, **kwargs) -> None:
    kafka_client.produce(
        T_TRANSACTION, key=user_id, value=build_transaction_event(user_id=user_id, **kwargs)
    )


# --- output topics --------------------------------------------------------------


def build_risk_score_event(
    *,
    entity_type: str,
    entity_id: str,
    behavior_score: float,
    device_score: float,
    transaction_score: float,
    final_risk_score: float,
    risk_band: str,
    model_version: str,
    trust_score: float | None = None,
    behavior_match_score: float | None = None,
    behavior_score_source: str | None = None,
    ts: str | None = None,
) -> dict:
    return RiskScoreEvent(
        entity_type=entity_type,
        entity_id=entity_id,
        behavior_score=behavior_score,
        device_score=device_score,
        transaction_score=transaction_score,
        final_risk_score=final_risk_score,
        risk_band=risk_band,
        model_version=model_version,
        trust_score=trust_score,
        behavior_match_score=behavior_match_score,
        behavior_score_source=behavior_score_source,
        ts=ts or _now_iso(),
    ).model_dump()


def emit_risk_score(**kwargs) -> None:
    kafka_client.produce(
        T_RISK_SCORES, key=kwargs["entity_id"], value=build_risk_score_event(**kwargs)
    )


def build_decision_event(
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    required_factors: list[str] | None = None,
    reason_codes: list[dict] | None = None,
    ts: str | None = None,
) -> dict:
    return DecisionEvent(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        required_factors=required_factors or [],
        reason_codes=reason_codes or [],
        ts=ts or _now_iso(),
    ).model_dump()


def emit_decision(**kwargs) -> None:
    kafka_client.produce(T_DECISIONS, key=kwargs["entity_id"], value=build_decision_event(**kwargs))
