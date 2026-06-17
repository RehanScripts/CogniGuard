import json

import pytest
import redis as redislib

import sinks

REDIS_URL = "redis://redis:6379/15"  # isolated test DB inside the compose network


@pytest.fixture()
def r():
    client = redislib.Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        client.ping()
    except Exception:
        pytest.skip("redis not reachable")
    client.flushdb()
    yield client
    client.flushdb()


def test_transaction_event_updates_velocity_and_profile(r):
    uid = "u1"
    for amt in (1000.0, 3000.0):  # mean 2000
        sinks.update_from_transaction_event(
            r, uid, {"amount": amt, "beneficiary_id": "b1", "ts": "t"}
        )
    assert r.get(sinks.k_velocity(uid, "1h")) == "2"
    assert r.get(sinks.k_velocity(uid, "24h")) == "2"
    assert float(r.get(sinks.k_amount_sum(uid))) == 4000.0
    prof = r.hgetall(sinks.k_profile(uid))
    assert float(prof["avg_amount_30d"]) == 2000.0
    assert int(prof["txn_count_30d"]) == 2
    assert r.sismember(sinks.k_known_benef(uid), "b1")
    # TTL window applied
    assert 0 < r.ttl(sinks.k_velocity(uid, "1h")) <= sinks.TTL_1H


def test_login_event_sets_known_device_and_baseline_geohash(r):
    uid = "u2"
    sinks.update_from_login_event(
        r, uid, {"device_id": "d1", "geo_lat": 19.07, "geo_lon": 72.87, "ts": "t1"}
    )
    assert r.sismember(sinks.k_known_devices(uid), "d1")
    prof = r.hgetall(sinks.k_profile(uid))
    assert prof["baseline_geohash"]  # first-seen location captured
    first_baseline = prof["baseline_geohash"]
    # a later login from a new geo must NOT overwrite the baseline
    sinks.update_from_login_event(
        r, uid, {"device_id": "d1", "geo_lat": 59.43, "geo_lon": 24.75, "ts": "t2"}
    )
    assert r.hget(sinks.k_profile(uid), "baseline_geohash") == first_baseline
    assert r.scard(sinks.k_known_geos(uid)) == 2


def test_device_event_zero_trust_for_rooted(r):
    sinks.update_from_device_event(r, "dev1", {"is_rooted": True})
    assert float(r.get(sinks.k_device_trust("dev1"))) == 0.0
    sinks.update_from_device_event(r, "dev2", {"is_rooted": False})
    assert float(r.get(sinks.k_device_trust("dev2"))) > 0.0


def test_behavior_event_builds_baseline(r):
    uid = "u3"
    for ts in (4.0, 6.0):  # typing_speed mean 5
        sinks.update_from_behavior_event(r, uid, {"typing_speed": ts})
    acc = json.loads(r.get(sinks.k_behavior_baseline(uid)))
    assert acc["_baseline"]["typing_speed"] == 5.0


def test_process_record_dispatch_no_s3(r):
    sinks.process_record(
        r, None, "cogniguard", "transaction_events", "u4", {"amount": 500.0, "ts": "t"}
    )
    assert r.get(sinks.k_velocity("u4", "1h")) == "1"
