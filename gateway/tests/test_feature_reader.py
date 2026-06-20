import json
import uuid

import pytest

from app import db as db_module
from app.redis_client import ping, redis_client
from app.schemas.behavior import ActionBlock, BehaviorPayload, DeviceInfo, MouseBlock
from app.schemas.features import FeatureReadContext
from app.scoring import calibration
from app.services import feature_reader as fr

pytestmark = pytest.mark.skipif(not ping(), reason="Redis not reachable")


def _behavior(**overrides) -> BehaviorPayload:
    defaults = dict(
        channel="web",
        source="web_sdk",
        nonce="test-nonce",
        seq=1,
        ts="2026-06-17T12:00:00Z",
        integrity_sig="deadbeef",
        device=DeviceInfo(fingerprint="fp"),
        action=ActionBlock(type="LOGIN"),
    )
    defaults.update(overrides)
    return BehaviorPayload(**defaults)


@pytest.fixture
def user_id():
    uid = f"feat-reader-test-{uuid.uuid4().hex}"
    yield uid
    for key in (
        f"user:{uid}:profile",
        f"user:{uid}:known_devices",
        f"user:{uid}:known_beneficiaries",
        f"user:{uid}:known_geos",
        f"user:{uid}:velocity:1h",
        f"user:{uid}:velocity:24h",
        f"user:{uid}:amount_sum:24h",
        calibration.user_calibration_key(uid),
    ):
        redis_client.delete(key)


@pytest.fixture
def session_id():
    sid = f"feat-reader-test-{uuid.uuid4().hex}"
    yield sid
    redis_client.delete(fr._k_seq(sid))


@pytest.fixture
def population_calibration():
    """Seeds the global population calibration key (Phase 16 normally does this) so
    ae_cold_start's "or no calibration available" branch can be exercised both ways."""
    redis_client.set(
        calibration.POPULATION_CALIBRATION_KEY,
        json.dumps({"scale": 1.0, "threshold": 0.5, "temperature": 1.0}),
    )
    yield
    redis_client.delete(calibration.POPULATION_CALIBRATION_KEY)


def test_read_bundle_never_touches_postgres(monkeypatch, user_id):
    def _boom(*args, **kwargs):
        raise AssertionError("read_bundle must not open a DB session")

    monkeypatch.setattr(db_module, "SessionLocal", _boom)

    ctx = FeatureReadContext(behavior=_behavior())
    fr.read_bundle(user_id, ctx, redis=redis_client)  # raises if it touches Postgres


def test_cold_start_defaults_bias_to_verify(user_id):
    ctx = FeatureReadContext(behavior=_behavior(), device_id="brand-new-device")
    bundle = fr.read_bundle(user_id, ctx, redis=redis_client)

    assert bundle.cold_start is True
    assert bundle.device.is_new_device is True
    assert bundle.txn.amount_zscore == 0.0
    assert bundle.txn.is_new_payee is False  # no beneficiary in this request


def test_amount_zscore_derived_from_profile(user_id):
    redis_client.hset(
        f"user:{user_id}:profile",
        mapping={"avg_amount_30d": "1000.0", "std_amount_30d": "200.0"},
    )

    ctx = FeatureReadContext(behavior=_behavior(), amount=1400.0)
    bundle = fr.read_bundle(user_id, ctx, redis=redis_client)

    assert bundle.cold_start is False
    assert bundle.txn.amount_zscore == pytest.approx((1400.0 - 1000.0) / 200.0)


def test_known_device_membership_respected(user_id):
    redis_client.sadd(f"user:{user_id}:known_devices", "trusted-device")

    known_ctx = FeatureReadContext(behavior=_behavior(), device_id="trusted-device")
    unknown_ctx = FeatureReadContext(behavior=_behavior(), device_id="stranger-device")

    known_bundle = fr.read_bundle(user_id, known_ctx, redis=redis_client)
    unknown_bundle = fr.read_bundle(user_id, unknown_ctx, redis=redis_client)

    assert known_bundle.device.is_new_device is False
    assert unknown_bundle.device.is_new_device is True


def test_known_beneficiary_membership_respected(user_id):
    redis_client.sadd(f"user:{user_id}:known_beneficiaries", "benef-1")

    known_ctx = FeatureReadContext(behavior=_behavior(), beneficiary_id="benef-1")
    new_ctx = FeatureReadContext(behavior=_behavior(), beneficiary_id="benef-2")

    known_bundle = fr.read_bundle(user_id, known_ctx, redis=redis_client)
    new_bundle = fr.read_bundle(user_id, new_ctx, redis=redis_client)

    assert known_bundle.txn.is_new_payee is False
    assert known_bundle.txn.beneficiary_risk == 0.0
    assert new_bundle.txn.is_new_payee is True
    assert new_bundle.txn.beneficiary_risk == fr.NEW_PAYEE_RISK


def test_mobile_derived_features_fold_through(user_id):
    behavior = _behavior(
        source="mobile_edge",
        derived_features={
            "swipe_velocity_norm": 1.4,
            "swipe_angle_dev": 0.2,
            "touch_pressure_avg": 0.5,
            "acceleration_variance": 0.03,
        },
    )
    ctx = FeatureReadContext(behavior=behavior)
    bundle = fr.read_bundle(user_id, ctx, redis=redis_client)

    assert bundle.behavior.swipe_velocity_norm == 1.4
    assert bundle.behavior.acceleration_variance == 0.03


def test_high_velocity_flag_from_counters(user_id):
    redis_client.set(f"user:{user_id}:velocity:1h", fr.HIGH_VELOCITY_1H)

    ctx = FeatureReadContext(behavior=_behavior())
    bundle = fr.read_bundle(user_id, ctx, redis=redis_client)

    assert bundle.txn.velocity_1h == fr.HIGH_VELOCITY_1H
    assert bundle.txn.high_velocity is True


# --- Phase 14: AE sequence buffer + cold-start gating ---------------------------------


def test_no_session_id_skips_sequence_buffer_entirely(user_id):
    """No caller passes session_id yet (that's Phase 15's job) -- existing callers must
    see byte-identical behavior: no Redis write, no sequence assembled."""
    ctx = FeatureReadContext(behavior=_behavior())
    bundle = fr.read_bundle(user_id, ctx, redis=redis_client)

    assert bundle.behavior_sequence is None
    assert bundle.behavior_sequence_mask is None
    assert bundle.ae_recon_error is None
    assert bundle.ae_cold_start is True


def test_web_first_push_pads_and_stays_cold_start(user_id, session_id):
    ctx = FeatureReadContext(behavior=_behavior(), session_id=session_id)
    bundle = fr.read_bundle(user_id, ctx, redis=redis_client)

    assert bundle.behavior_sequence is not None
    assert len(bundle.behavior_sequence) == fr.SEQ_LEN
    assert bundle.behavior_sequence_mask == [False] * (fr.SEQ_LEN - 1) + [True]
    assert bundle.ae_cold_start is True  # 1 real row < MIN_SEQ


def test_web_cold_start_clears_once_min_seq_and_calibration_present(
    user_id, session_id, population_calibration
):
    ctx = FeatureReadContext(behavior=_behavior(), session_id=session_id)
    bundle = None
    for _ in range(fr.MIN_SEQ):
        bundle = fr.read_bundle(user_id, ctx, redis=redis_client)

    assert sum(bundle.behavior_sequence_mask) == fr.MIN_SEQ
    assert bundle.ae_cold_start is False


def test_web_cold_start_stays_true_without_calibration_even_past_min_seq(user_id, session_id):
    ctx = FeatureReadContext(behavior=_behavior(), session_id=session_id)
    bundle = None
    for _ in range(fr.MIN_SEQ):
        bundle = fr.read_bundle(user_id, ctx, redis=redis_client)

    assert sum(bundle.behavior_sequence_mask) == fr.MIN_SEQ
    assert bundle.ae_cold_start is True  # enough samples, but no calibration seeded


def test_web_sequence_buffer_caps_at_seq_len_and_trims_oldest(user_id, session_id):
    mouse_idx = fr.BEHAVIOR_COLUMNS.index("mouse_velocity_mean")
    bundle = None
    for i in range(fr.SEQ_LEN + 4):
        behavior = _behavior(
            mouse=MouseBlock(moves=[{"x": 0, "y": 0, "t": 0}, {"x": i * 10, "y": 0, "t": 10}])
        )
        ctx = FeatureReadContext(behavior=behavior, session_id=session_id)
        bundle = fr.read_bundle(user_id, ctx, redis=redis_client)

    real_values = [
        row[mouse_idx]
        for row, is_real in zip(bundle.behavior_sequence, bundle.behavior_sequence_mask)
        if is_real
    ]
    assert len(real_values) == fr.SEQ_LEN
    assert min(real_values) == 4.0  # i=0..3 trimmed away
    assert max(real_values) == float(fr.SEQ_LEN + 3)


def test_mobile_ae_recon_error_folds_through_with_no_redis_write(user_id, session_id):
    behavior = _behavior(
        channel="mobile",
        source="mobile_edge",
        derived_features={"swipe_velocity_norm": 1.0},
        ae_recon_error=0.42,
    )
    ctx = FeatureReadContext(behavior=behavior, session_id=session_id)
    bundle = fr.read_bundle(user_id, ctx, redis=redis_client)

    assert bundle.ae_recon_error == 0.42
    assert bundle.behavior_sequence is None
    assert bundle.behavior_sequence_mask is None
    assert redis_client.exists(fr._k_seq(session_id)) == 0  # mobile never writes the buffer


def test_mobile_without_ae_recon_error_is_cold_start(user_id):
    behavior = _behavior(channel="mobile", source="mobile_edge", derived_features={})
    ctx = FeatureReadContext(behavior=behavior)
    bundle = fr.read_bundle(user_id, ctx, redis=redis_client)

    assert bundle.ae_recon_error is None
    assert bundle.ae_cold_start is True


def test_mobile_cold_start_clears_with_recon_error_and_calibration_present(
    user_id, population_calibration
):
    behavior = _behavior(
        channel="mobile", source="mobile_edge", derived_features={}, ae_recon_error=0.1
    )
    ctx = FeatureReadContext(behavior=behavior)
    bundle = fr.read_bundle(user_id, ctx, redis=redis_client)

    assert bundle.ae_recon_error == 0.1
    assert bundle.ae_cold_start is False
