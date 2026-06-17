"""Geo helpers for the gateway (Implementation.md Phase 5).

Mirrors `flink-jobs/windows.py` byte-for-byte: the gateway computes `geohash` at
read time to look up `user:{id}:known_geos` (written by Flink in the same encoding),
so the two implementations must stay identical. Flink ships as a separate Python
image and can't be imported here, hence the small duplication.
"""

from __future__ import annotations

import math

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
    """Standard geohash encoder (base32) — must match flink-jobs/windows.py exactly."""
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
