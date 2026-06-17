from app.scoring.amplifiers import (
    COERCION_DWELL_MS,
    DRAIN_BALANCE_RATIO,
    NEW_PAYEE_WINDOW_MIN,
    RAPID_FANOUT_MIN_PAYEES,
    TxnContext,
    apply,
    evaluate,
)

POLICY_AMPS = {"NEW_BENEF_HIGHVAL": 1.5, "RAPID_FANOUT": 1.4, "DRAIN": 1.3, "COERCION_TIME": 1.2}


def test_new_benef_highval_fires():
    ctx = TxnContext(payee_age_minutes=30, daily_avg_amount=1000, amount=900)
    fired = evaluate(ctx, POLICY_AMPS)
    assert [a.code for a in fired] == ["NEW_BENEF_HIGHVAL"]
    assert fired[0].multiplier == 1.5


def test_new_benef_highval_does_not_fire_for_old_payee():
    ctx = TxnContext(payee_age_minutes=NEW_PAYEE_WINDOW_MIN + 1, daily_avg_amount=1000, amount=900)
    assert evaluate(ctx, POLICY_AMPS) == []


def test_apply_clamp_base_25_to_37_5():
    fired = evaluate(
        TxnContext(payee_age_minutes=30, daily_avg_amount=1000, amount=900), POLICY_AMPS
    )
    assert apply(25, fired) == 37.5


def test_apply_clamps_at_100():
    ctx = TxnContext(
        payee_age_minutes=30,
        daily_avg_amount=1000,
        amount=900,
        new_payee_count_recent=RAPID_FANOUT_MIN_PAYEES,
    )
    fired = evaluate(ctx, POLICY_AMPS)
    assert len(fired) == 2  # NEW_BENEF_HIGHVAL (1.5) + RAPID_FANOUT (1.4)
    assert apply(90, fired) == 100.0


def test_rapid_fanout_fires_at_threshold():
    fires = evaluate(TxnContext(new_payee_count_recent=RAPID_FANOUT_MIN_PAYEES), POLICY_AMPS)
    no_fire = evaluate(TxnContext(new_payee_count_recent=RAPID_FANOUT_MIN_PAYEES - 1), POLICY_AMPS)
    assert [a.code for a in fires] == ["RAPID_FANOUT"]
    assert no_fire == []


def test_drain_fires():
    ctx = TxnContext(
        payee_age_minutes=10, account_balance=10000, amount=DRAIN_BALANCE_RATIO * 10000 + 1
    )
    fired = evaluate(ctx, POLICY_AMPS)
    assert [a.code for a in fired] == ["DRAIN"]


def test_drain_does_not_fire_below_threshold():
    ctx = TxnContext(
        payee_age_minutes=10, account_balance=10000, amount=DRAIN_BALANCE_RATIO * 10000 - 100
    )
    assert evaluate(ctx, POLICY_AMPS) == []


def test_coercion_time_fires():
    fired = evaluate(TxnContext(odd_time=True, pre_txn_dwell_ms=COERCION_DWELL_MS), POLICY_AMPS)
    assert [a.code for a in fired] == ["COERCION_TIME"]


def test_coercion_time_requires_both_conditions():
    assert evaluate(TxnContext(odd_time=True, pre_txn_dwell_ms=0), POLICY_AMPS) == []
    assert (
        evaluate(TxnContext(odd_time=False, pre_txn_dwell_ms=COERCION_DWELL_MS), POLICY_AMPS) == []
    )


def test_no_amplifiers_fire_on_clean_context():
    assert evaluate(TxnContext(), POLICY_AMPS) == []


def test_multipliers_come_only_from_policy():
    ctx = TxnContext(payee_age_minutes=30, daily_avg_amount=1000, amount=900)
    fired_a = evaluate(ctx, {**POLICY_AMPS, "NEW_BENEF_HIGHVAL": 1.5})
    fired_b = evaluate(ctx, {**POLICY_AMPS, "NEW_BENEF_HIGHVAL": 2.0})
    assert fired_a[0].multiplier == 1.5
    assert fired_b[0].multiplier == 2.0
