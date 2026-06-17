import math

from windows import (
    geo_velocity_kmh,
    geohash,
    haversine,
    welford_std,
    welford_update,
    zscore,
)


def test_haversine_zero_for_same_point():
    assert haversine(19.07, 72.87, 19.07, 72.87) == 0.0


def test_haversine_mumbai_tallinn():
    km = haversine(19.07, 72.87, 59.43, 24.75)  # impossible-travel demo pair
    assert 5800 < km < 6700  # ~6300 km


def test_geohash_known_value():
    # Classic Wikipedia example: (57.64911, 10.40744) -> "u4pruydqqvj..."
    assert geohash(57.64911, 10.40744, 5) == "u4pru"
    assert geohash(57.64911, 10.40744, 7).startswith("u4pruyd")


def test_geohash_precision_length():
    assert len(geohash(19.07, 72.87, 9)) == 9


def test_zscore_basic_and_guard():
    assert zscore(5.0, 1.0, 2.0) == 2.0
    assert zscore(1.0, 1.0, 0.0) == 0.0  # no div-by-zero; delta 0 → 0


def test_welford_mean_and_std():
    # 2,4,4,4,5,5,7,9 -> mean 5, population variance 4, std 2
    count, mean, m2 = 0, 0.0, 0.0
    for x in [2, 4, 4, 4, 5, 5, 7, 9]:
        count, mean, m2 = welford_update(count, mean, m2, x)
    assert mean == 5.0
    assert math.isclose(welford_std(count, m2), 2.0, rel_tol=1e-9)


def test_welford_std_under_two_samples():
    count, mean, m2 = welford_update(0, 0.0, 0.0, 42.0)
    assert welford_std(count, m2) == 0.0


def test_geo_velocity_kmh():
    assert geo_velocity_kmh(900, 3600) == 900.0  # 900 km in 1h
    assert geo_velocity_kmh(100, 0) == float("inf")  # instantaneous over distance
    assert geo_velocity_kmh(0, 0) == 0.0
