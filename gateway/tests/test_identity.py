"""Continuous identity verification (Implementation.md Phase 20-23).

Covers the per-user identity scorer, the data-driven enrollment service (no seeding),
and the identity+trust layer wired into `stack.score` -- including the explicit guard
that the LSTM Autoencoder stays *active* (genuineness term + still feeds XGBoost), not
demoted to shadow. Pure-logic unit tests with dict/list-backed fakes, same style as
test_stack_ae.py / test_calibration.py -- no live Postgres/Redis.
"""

from __future__ import annotations

import json

import pytest

from app.schemas.features import BehaviorFeatures, FeatureBundle
from app.scoring import calibration, identity, stack
from app.scoring.calibration import CalibrationParams
from app.scoring.registry import LoadedModel
from app.services import enrollment
from training.train_isolation_forest import BEHAVIOR_COLUMNS
from training.train_xgboost import FEATURE_COLUMNS

N = len(BEHAVIOR_COLUMNS)
_BSCORE_IDX = FEATURE_COLUMNS.index("behavior_score")

POLICY = {
    "thresholds": {"low_max": 30, "medium_max": 60, "very_high_min": 85},
    "amplifiers": {
        "NEW_BENEF_HIGHVAL": 1.5,
        "RAPID_FANOUT": 1.4,
        "DRAIN": 1.3,
        "COERCION_TIME": 1.2,
    },
    "scoring_mode": "stacked",
    "trust_weights": {
        "support": {"genuineness": 0.5, "device": 0.3, "env": 0.2},
        "env_penalty": {"geo_change": 0.4, "new_device": 0.4, "vpn": 0.2},
    },
    "enrollment": {"min_sessions": 10},
}


# --------------------------------------------------------------------------- fakes
class _FakeRedis:
    """dict-backed fake supporting the string + list ops enrollment/feature_reader use."""

    def __init__(self, data: dict | None = None):
        self._data = dict(data or {})

    def get(self, key):
        v = self._data.get(key)
        return v if not isinstance(v, list) else None

    def set(self, key, value, ex=None):
        self._data[key] = value

    def exists(self, key):
        return 1 if key in self._data else 0

    def delete(self, key):
        self._data.pop(key, None)

    def rpush(self, key, value):
        self._data.setdefault(key, []).append(value)
        return len(self._data[key])

    def llen(self, key):
        v = self._data.get(key, [])
        return len(v) if isinstance(v, list) else 0

    def lrange(self, key, start, end):
        lst = self._data.get(key, [])
        n = len(lst)
        s = max(n + start, 0) if start < 0 else start
        e = (n + end) if end < 0 else end
        return lst[s : e + 1]

    def ltrim(self, key, start, end):
        lst = self._data.get(key, [])
        n = len(lst)
        s = max(n + start, 0) if start < 0 else start
        e = (n + end) if end < 0 else end
        self._data[key] = lst[s : e + 1]

    def expire(self, key, ttl):
        return True


class _StubIFModel:
    def __init__(self, raw: float = 0.0):
        self._raw = raw

    def decision_function(self, X):
        return [self._raw]


class _BscoreEchoXGB:
    """fraud prob derived purely from the behavior_score feature -> proves bscore (AE)
    still flows into XGBoost."""

    def predict_proba(self, X):
        b = X[0][_BSCORE_IDX]
        p = 0.1 + 0.5 * b
        return [[1 - p, p]]


class _FakeRegistry:
    def __init__(self, models):
        self._models = models

    def get(self, name):
        return LoadedModel(
            model_name=name, version=f"{name}@test", model=self._models[name], artifact_uri=""
        )


def _registry():
    return _FakeRegistry({"isolation_forest": _StubIFModel(0.0), "xgboost_txn": _BscoreEchoXGB()})


def _baseline(stats=None, *, scale=0.5, threshold=2.0):
    stats = stats or {name: (0.0, 1.0) for name in BEHAVIOR_COLUMNS}
    return identity.IdentityBaseline(
        stats=stats,
        distance_calib=CalibrationParams(scale=scale, threshold=threshold),
        count=10,
        enrolled_at="2026-06-22T00:00:00+00:00",
    )


# ----------------------------------------------------------------- identity scorer
def test_match_high_for_vector_at_baseline_low_for_far():
    base = _baseline()
    near = identity.behavior_match_score([0.0] * N, base)
    far = identity.behavior_match_score([50.0] + [0.0] * (N - 1), base)
    assert near > 95
    assert far < 5


def test_zero_mad_dim_does_not_explode_distance():
    """Regression: a baseline dim with `mad=0` must not produce an infinite robust-z on
    any live deviation (the bug that false-blocked genuine logins against a synthetic
    baseline where e.g. hold_time was a constant 80ms). A constant non-zero dim yields a
    bounded distance; a constant *zero* dim carries no info and is skipped, so a pure
    channel difference (web baseline, mobile swipe) doesn't blow up the match."""
    stats = {name: (0.0, 1.0) for name in BEHAVIOR_COLUMNS}
    stats["hold_time_avg"] = (80.0, 0.0)  # constant non-zero, no spread
    stats["swipe_velocity_norm"] = (0.0, 0.0)  # constant zero -> no identity info
    base = _baseline(stats=stats, scale=6.0, threshold=50.0)

    # Live vector at the baseline medians (hold_time=80, swipe=0) is a near-perfect match.
    at_baseline = [0.0] * N
    at_baseline[BEHAVIOR_COLUMNS.index("hold_time_avg")] = 80.0
    assert identity.identity_distance(at_baseline, base) < 1.0
    assert identity.behavior_match_score(at_baseline, base) > 90

    # A genuine hold-time wobble (80 -> 95ms) stays bounded, not astronomically far.
    wobble = list(at_baseline)
    wobble[BEHAVIOR_COLUMNS.index("hold_time_avg")] = 95.0
    assert identity.identity_distance(wobble, base) < 5.0

    # A nonzero live swipe (mobile) against the zero/zero swipe dim must NOT explode --
    # the dim is skipped, so the distance stays driven by the informative dims only.
    swiping = list(at_baseline)
    swiping[BEHAVIOR_COLUMNS.index("swipe_velocity_norm")] = 1200.0
    assert identity.identity_distance(swiping, base) < 1.0


def test_compute_trust_identity_gates_support():
    """A poor identity match cannot be rescued by strong device/AE (multiplicative
    anchor); cold-start (match None) falls back to support only."""
    strong_support = dict(genuineness=100.0, device_trust=100.0, env_consistency=100.0,
                          support_weights=POLICY["trust_weights"]["support"])
    good = identity.compute_trust(behavior_match=95.0, **strong_support)
    impostor = identity.compute_trust(behavior_match=20.0, **strong_support)
    coldstart = identity.compute_trust(behavior_match=None, **strong_support)
    assert good.trust_score > 90
    assert impostor.trust_score < 25  # strong device/AE can't save a bad identity match
    assert coldstart.trust_score == pytest.approx(100.0)  # support only, no gate
    assert coldstart.behavior_match is None


def test_env_consistency_penalizes_anomalous_context():
    w = POLICY["trust_weights"]["env_penalty"]
    clean = identity.env_consistency(geo_change=False, new_device=False, vpn=False, weights=w)
    dirty = identity.env_consistency(geo_change=True, new_device=True, vpn=True, weights=w)
    assert clean == pytest.approx(100.0)
    assert dirty < clean


# ------------------------------------------------------------ data-driven enrollment
def _vec(seed: float) -> list[float]:
    return [seed + 0.1 * i for i in range(N)]


def test_enrollment_is_data_driven_not_seeded():
    redis = _FakeRedis()
    uid = "rehan"
    ikey = identity.identity_baseline_key(uid)
    aekey = calibration.user_calibration_key(uid)

    # Nothing exists before enrollment, and nothing is written before `required` is hit.
    assert redis.exists(ikey) == 0
    for i in range(9):
        prog = enrollment.record(
            uid, _vec(5.0 + 0.01 * i), 0.2 + 0.01 * i, required=10, redis=redis
        )
        assert prog.complete is False
        assert redis.exists(ikey) == 0  # never written mid-enrollment

    final = enrollment.record(uid, _vec(5.05), 0.25, required=10, redis=redis)
    assert final.complete is True and final.just_finalized is True
    assert redis.exists(ikey) == 1  # written only on the cycle that reached required

    # The persisted baseline is DERIVED from the fed sessions, not a default/seed.
    parsed = identity.parse_identity_baseline(redis.get(ikey))
    assert parsed is not None and parsed.count == 10
    default = calibration.default_calibration()
    assert (parsed.distance_calib.scale, parsed.distance_calib.threshold) != (
        default.scale,
        default.threshold,
    )
    # >=5 AE recon errors captured -> per-user ae_calib fit (also data-derived).
    assert redis.exists(aekey) == 1
    ae = json.loads(redis.get(aekey))
    assert ae["threshold"] != default.threshold


def test_enrollment_skips_ae_calib_when_too_few_recon_errors():
    redis = _FakeRedis()
    uid = "weben"  # web-style: no per-cycle AE recon error available at login
    for i in range(10):
        enrollment.record(uid, _vec(3.0 + 0.01 * i), None, required=10, redis=redis)
    assert redis.exists(identity.identity_baseline_key(uid)) == 1  # baseline still built
    assert redis.exists(calibration.user_calibration_key(uid)) == 0  # no fabricated ae_calib


# --------------------------------------------------- identity layer in stack.score
def _enrolled_bundle(behavior: BehaviorFeatures, baseline, *, device_trust=80.0, recon=0.0):
    return FeatureBundle(
        user_id="u1",
        behavior=behavior,
        device={"device_trust": device_trust, "is_new_device": False, "is_rooted": False},
        ae_cold_start=False,
        ae_recon_error=recon,  # mobile path
        identity_baseline=baseline,
        enrolled=True,
    )


# population calib with a high threshold so a low recon error -> low bscore -> high genuineness
_REDIS_LOWANOM = _FakeRedis(
    {
        calibration.POPULATION_CALIBRATION_KEY: json.dumps(
            {"scale": 1.0, "threshold": 5.0, "temperature": 1.0}
        )
    }
)


def test_enrolled_match_allows_low_band():
    base = _baseline()
    result = stack.score(
        _enrolled_bundle(BehaviorFeatures(), base),  # all-zero vector == baseline median
        policy=POLICY, registry=_registry(), redis=_REDIS_LOWANOM,
    )
    assert result.behavior_match_score is not None and result.behavior_match_score > 90
    assert result.risk_band == "low"
    assert result.final_risk_score == pytest.approx(result.identity_risk)
    assert not any(rc.code == "BEHAVIOR_IDENTITY_MISMATCH" for rc in result.reason_codes)


def test_enrolled_mismatch_escalates_with_reason_code():
    base = _baseline()
    impostor = BehaviorFeatures(typing_speed=50.0)  # far from the all-zero baseline
    result = stack.score(
        _enrolled_bundle(impostor, base),
        policy=POLICY, registry=_registry(), redis=_REDIS_LOWANOM,
    )
    assert result.behavior_match_score < 40
    assert result.risk_band == "very_high"
    assert any(rc.code == "BEHAVIOR_IDENTITY_MISMATCH" for rc in result.reason_codes)


def test_ae_stays_active_degraded_genuineness_lowers_trust_and_feeds_xgboost():
    """AE not demoted to shadow: with the SAME high identity match, a degraded AE
    (high recon error -> high bscore -> low genuineness) reduces the Trust Score, AND the
    higher bscore still flows into XGBoost (transaction_score rises)."""
    base = _baseline()
    good = stack.score(_enrolled_bundle(BehaviorFeatures(), base, recon=0.0),
                       policy=POLICY, registry=_registry(), redis=_REDIS_LOWANOM)
    degraded = stack.score(_enrolled_bundle(BehaviorFeatures(), base, recon=20.0),
                           policy=POLICY, registry=_registry(), redis=_REDIS_LOWANOM)

    assert good.behavior_match_score == pytest.approx(  # same identity
        degraded.behavior_match_score
    )
    assert degraded.behavior_score > good.behavior_score  # AE saw the anomaly
    assert degraded.trust_score < good.trust_score  # genuineness term pulled trust down
    assert degraded.transaction_score > good.transaction_score  # bscore still feeds XGBoost


def test_cold_start_not_enrolled_keeps_legacy_score_and_no_identity_gate():
    """No baseline -> identity gate inactive -> acted-on score is the existing XGBoost/IF
    path (unchanged), behavior_match None, never blocked purely for being new."""
    bundle = FeatureBundle(user_id="u1")  # enrolled defaults False, no baseline
    result = stack.score(bundle, policy=POLICY, registry=_registry(), redis=_FakeRedis())
    assert result.behavior_match_score is None
    assert result.final_risk_score == pytest.approx(result.base_score)  # legacy path intact
