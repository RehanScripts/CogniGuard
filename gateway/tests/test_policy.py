import json

from app.services.policy import DEFAULT_POLICY, POLICY_REDIS_KEY, active_policy

_REQUIRED_KEYS = {
    "scoring_mode",
    "weights",
    "thresholds",
    "action_sensitivity",
    "amplifiers",
    "stepup",
    "cooling_off",
    "hardening",
}


class _FakeRedis:
    def __init__(self, value: str | None = None, *, raise_on_get: bool = False):
        self._value = value
        self._raise = raise_on_get

    def get(self, key: str) -> str | None:
        if self._raise:
            raise RuntimeError("redis unreachable")
        return self._value if key == POLICY_REDIS_KEY else None


def test_no_redis_returns_defaults():
    policy = active_policy(redis=None)
    assert _REQUIRED_KEYS <= policy.keys()
    assert policy["thresholds"] == DEFAULT_POLICY["thresholds"]
    assert policy == DEFAULT_POLICY


def test_default_policy_is_not_mutated_by_callers():
    policy = active_policy(redis=None)
    policy["thresholds"]["low_max"] = 999
    assert DEFAULT_POLICY["thresholds"]["low_max"] == 30


def test_redis_overlay_overrides_only_specified_keys():
    overlay = json.dumps({"thresholds": {"low_max": 20}})
    policy = active_policy(redis=_FakeRedis(overlay))
    assert policy["thresholds"]["low_max"] == 20
    assert policy["thresholds"]["medium_max"] == DEFAULT_POLICY["thresholds"]["medium_max"]
    assert policy["amplifiers"] == DEFAULT_POLICY["amplifiers"]


def test_empty_redis_key_falls_back_to_defaults():
    policy = active_policy(redis=_FakeRedis(None))
    assert policy == DEFAULT_POLICY


def test_malformed_redis_value_falls_back_to_defaults():
    policy = active_policy(redis=_FakeRedis("not json"))
    assert policy == DEFAULT_POLICY


def test_redis_failure_does_not_propagate():
    policy = active_policy(redis=_FakeRedis(raise_on_get=True))
    assert policy == DEFAULT_POLICY
