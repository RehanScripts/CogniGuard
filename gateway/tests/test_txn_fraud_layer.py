"""Phase 7 acceptance check (Implementation.md lines 467-475)."""

import datetime as dt

from app.scoring.amplifiers import TxnContext, evaluate
from app.services.policy import DEFAULT_POLICY
from app.services.txn_fraud_layer import resolve_controls

POLICY = DEFAULT_POLICY


def test_clean_medium_band_no_amplifiers_no_controls():
    controls = resolve_controls("medium", [], TxnContext(), POLICY)
    assert controls.cooling_until is None
    assert controls.manual_amount is False
    assert controls.coercion_check is False
    assert controls.reconfirm is None


def test_coercion_time_fires_controls_even_on_medium_band():
    ctx = TxnContext(odd_time=True, pre_txn_dwell_ms=30_000)
    amps = evaluate(ctx, POLICY["amplifiers"])
    assert [a.code for a in amps] == ["COERCION_TIME"]

    controls = resolve_controls("medium", amps, ctx, POLICY)
    assert controls.coercion_check is True
    assert controls.manual_amount is True
    # COERCION_TIME alone doesn't force cooling/reconfirm
    assert controls.cooling_until is None


def test_new_benef_highval_on_low_band_genuine_behavior_still_gets_cooling():
    ctx = TxnContext(payee_age_minutes=30, daily_avg_amount=1000, amount=900)
    amps = evaluate(ctx, POLICY["amplifiers"])
    assert [a.code for a in amps] == ["NEW_BENEF_HIGHVAL"]

    controls = resolve_controls("low", amps, ctx, POLICY)
    assert controls.manual_amount is True
    assert controls.cooling_until is not None
    parsed = dt.datetime.fromisoformat(controls.cooling_until)
    assert parsed > dt.datetime.now(dt.timezone.utc)


def test_high_band_gets_full_scrutiny_even_with_no_amplifiers():
    controls = resolve_controls("high", [], TxnContext(), POLICY)
    assert controls.reconfirm == "APP_PUSH"
    assert controls.manual_amount is True
    assert controls.coercion_check is True


def test_very_high_band_gets_full_scrutiny():
    controls = resolve_controls("very_high", [], TxnContext(), POLICY)
    assert controls.reconfirm == "APP_PUSH"
    assert controls.manual_amount is True
    assert controls.coercion_check is True


def test_cooling_minutes_come_from_policy_not_hardcoded():
    ctx = TxnContext(payee_age_minutes=30, daily_avg_amount=1000, amount=900)
    amps = evaluate(ctx, POLICY["amplifiers"])
    custom_policy = {**POLICY, "cooling_off": {"minutes": 5, "reconfirm_channel": "EMAIL"}}

    controls = resolve_controls("low", amps, ctx, custom_policy)

    until = dt.datetime.fromisoformat(controls.cooling_until)
    now = dt.datetime.now(dt.timezone.utc)
    assert dt.timedelta(minutes=4) < (until - now) <= dt.timedelta(minutes=5)
