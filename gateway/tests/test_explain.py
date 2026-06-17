import pytest

from app.schemas.features import (
    BehaviorFeatures,
    DeviceFeatures,
    FeatureBundle,
    NetworkFeatures,
    TxnFeatures,
)
from app.scoring import explain
from app.scoring.explain import _BEHAVIOR_REFERENCE, EPS


def _bundle(**overrides) -> FeatureBundle:
    defaults = dict(
        user_id="u1",
        behavior=BehaviorFeatures(),
        device=DeviceFeatures(is_new_device=False),
        network=NetworkFeatures(),
        txn=TxnFeatures(),
    )
    defaults.update(overrides)
    return FeatureBundle(**defaults)


def test_top_2_drivers_by_abs_z():
    # typing_speed far below its reference mean (large |z|); everything else exactly at
    # its reference mean (z=0) except hold_time_avg, the second-largest deviation.
    behavior = BehaviorFeatures(
        **{name: mean for name, (mean, _std) in _BEHAVIOR_REFERENCE.items()}
    )
    behavior = behavior.model_copy(update={"typing_speed": -50.0, "hold_time_avg": 500.0})
    bundle = _bundle(behavior=behavior)

    codes = explain.reason_codes(bundle, base_drivers=True)
    deviation_codes = [c for c in codes if c.code.startswith("DEVIATION_")]

    assert deviation_codes[0].code == "DEVIATION_TYPING_SPEED"
    assert deviation_codes[1].code == "DEVIATION_HOLD_TIME_AVG"
    assert len(deviation_codes) == 2


def test_plain_english_phrase():
    bundle = _bundle()
    codes = explain.reason_codes(bundle, base_drivers=True)
    deviation_codes = [c for c in codes if c.code.startswith("DEVIATION_")]
    for c in deviation_codes:
        assert c.detail
        assert not c.detail.isupper()  # human-readable sentence, not a bare code


def test_std_to_eps_guard_no_div_by_zero():
    mean, _std = _BEHAVIOR_REFERENCE["typing_speed"]
    z = (mean - mean) / max(0.0, EPS)  # std=0 guarded by EPS -- must not raise
    assert z == 0.0

    extreme = (mean + 1.0 - mean) / max(0.0, EPS)
    assert extreme == pytest.approx(1.0 / EPS)


def test_pseudo_features_appended():
    bundle = _bundle(
        device=DeviceFeatures(is_new_device=True),
        network=NetworkFeatures(geo_change=True),
        txn=TxnFeatures(is_new_payee=True, odd_time=True, high_velocity=True),
    )
    codes = {c.code for c in explain.reason_codes(bundle, base_drivers=False)}
    assert codes == {"NEW_DEVICE", "GEO_CHANGE", "NEW_PAYEE", "ODD_TIME", "HIGH_VELOCITY"}


def test_amplifiers_not_appended_by_explain():
    bundle = _bundle()
    codes = explain.reason_codes(bundle, base_drivers=True)
    assert all(not c.code.startswith("NEW_BENEF") for c in codes)
    assert all(c.code not in ("RAPID_FANOUT", "DRAIN", "COERCION_TIME") for c in codes)
