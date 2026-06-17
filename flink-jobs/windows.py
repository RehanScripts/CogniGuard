"""Pure feature-math helpers used by the Flink feature engine and the read-time
feature_reader. No Flink / Redis / IO here — fully unit-testable.

Windowing strategy (Architecture §4.1): rolling velocity/sum windows are enforced by
Redis key TTLs (counters with EXPIRE), while 30-day profile stats are maintained
incrementally (Welford). These helpers cover the stateless math: geo distance, geohash,
z-score, and the incremental mean/variance update.
"""

from __future__ import annotations

import math

EPS = 1e-9
_GEOHASH_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two lat/lon points."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def geohash(lat: float, lon: float, precision: int = 7) -> str:
    """Standard geohash encoder (base32). Deterministic; used for baseline_geohash
    and the known_geos set."""
    lat_range = [-90.0, 90.0]
    lon_range = [-180.0, 180.0]
    out: list[str] = []
    bit = 0
    ch = 0
    even = True
    while len(out) < precision:
        if even:  # bisect longitude
            mid = (lon_range[0] + lon_range[1]) / 2
            if lon >= mid:
                ch = (ch << 1) | 1
                lon_range[0] = mid
            else:
                ch = ch << 1
                lon_range[1] = mid
        else:  # bisect latitude
            mid = (lat_range[0] + lat_range[1]) / 2
            if lat >= mid:
                ch = (ch << 1) | 1
                lat_range[0] = mid
            else:
                ch = ch << 1
                lat_range[1] = mid
        even = not even
        bit += 1
        if bit == 5:
            out.append(_GEOHASH_BASE32[ch])
            bit = 0
            ch = 0
    return "".join(out)


def zscore(x: float, mean: float, std: float) -> float:
    """Standardized deviation, guarded against zero std."""
    return (x - mean) / max(std, EPS)


def welford_update(count: int, mean: float, m2: float, x: float) -> tuple[int, float, float]:
    """Online mean/variance accumulation (Welford). Returns updated (count, mean, m2)."""
    count += 1
    delta = x - mean
    mean += delta / count
    m2 += delta * (x - mean)
    return count, mean, m2


def welford_std(count: int, m2: float) -> float:
    """Population std from Welford accumulators (0 for <2 samples)."""
    if count < 2:
        return 0.0
    return math.sqrt(m2 / count)


def geo_velocity_kmh(km: float, seconds: float) -> float:
    """Implied travel speed (km/h). inf if instantaneous over distance."""
    if seconds <= 0:
        return float("inf") if km > 0 else 0.0
    return km / (seconds / 3600.0)
