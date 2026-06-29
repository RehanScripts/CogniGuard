"""Unit tests for the Device Trust Engine (UPGRADE_PLAN.md Phase B1).

Pure-logic tests — no Redis, no I/O.  Covers every trust branch and the
hours_since() helper.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.scoring.device_trust import DeviceTrustResult, _BUDGET_DEFAULTS, compute, hours_since


# ── compute() ─────────────────────────────────────────────────────────────────


def test_rooted_device_is_suspicious() -> None:
    result = compute(
        is_rooted=True,
        is_emulator=False,
        is_new_device=False,
        geo_distance_km=0.0,
        hours_since_last_login=None,
    )
    assert result.device_class == "suspicious"
    assert result.trust <= 10.0


def test_emulator_is_suspicious() -> None:
    result = compute(
        is_rooted=False,
        is_emulator=True,
        is_new_device=False,
        geo_distance_km=0.0,
        hours_since_last_login=None,
    )
    assert result.device_class == "suspicious"
    assert result.trust <= 10.0


def test_known_clean_device_is_known_or_trusted() -> None:
    result = compute(
        is_rooted=False,
        is_emulator=False,
        is_new_device=False,
        geo_distance_km=0.0,
        hours_since_last_login=None,
    )
    assert result.device_class in ("known", "trusted")
    assert result.trust >= 50.0


def test_new_device_class() -> None:
    result = compute(
        is_rooted=False,
        is_emulator=False,
        is_new_device=True,
        geo_distance_km=0.0,
        hours_since_last_login=None,
    )
    assert result.device_class in ("new", "known")
    assert result.trust < 60.0


def test_impossible_travel_lowers_trust() -> None:
    # 2000 km in 1 hour → 2000 km/h, well above 800 km/h threshold
    normal = compute(
        is_rooted=False,
        is_emulator=False,
        is_new_device=False,
        geo_distance_km=0.0,
        hours_since_last_login=1.0,
    )
    imposs = compute(
        is_rooted=False,
        is_emulator=False,
        is_new_device=False,
        geo_distance_km=2000.0,
        hours_since_last_login=1.0,
    )
    assert imposs.trust < normal.trust
    assert imposs.signals["impossible_travel"] is True


def test_no_impossible_travel_when_speed_below_threshold() -> None:
    # 500 km in 1 hour = 500 km/h < 800 km/h
    result = compute(
        is_rooted=False,
        is_emulator=False,
        is_new_device=False,
        geo_distance_km=500.0,
        hours_since_last_login=1.0,
    )
    assert result.signals["impossible_travel"] is False


def test_no_impossible_travel_without_last_login() -> None:
    result = compute(
        is_rooted=False,
        is_emulator=False,
        is_new_device=False,
        geo_distance_km=5000.0,
        hours_since_last_login=None,
    )
    assert result.signals["impossible_travel"] is False


def test_biometric_bonus_raises_trust() -> None:
    without = compute(
        is_rooted=False,
        is_emulator=False,
        is_new_device=False,
        geo_distance_km=0.0,
        hours_since_last_login=None,
        biometric_bound=False,
    )
    with_ = compute(
        is_rooted=False,
        is_emulator=False,
        is_new_device=False,
        geo_distance_km=0.0,
        hours_since_last_login=None,
        biometric_bound=True,
    )
    assert with_.trust > without.trust


def test_trust_clamped_to_100() -> None:
    result = compute(
        is_rooted=False,
        is_emulator=False,
        is_new_device=False,
        geo_distance_km=0.0,
        hours_since_last_login=None,
        biometric_bound=True,
    )
    assert result.trust <= 100.0


def test_trust_clamped_to_zero_floor() -> None:
    # Impossible travel on a new device — trust may go negative internally
    result = compute(
        is_rooted=False,
        is_emulator=False,
        is_new_device=True,
        geo_distance_km=9999.0,
        hours_since_last_login=0.001,
    )
    assert result.trust >= 0.0


def test_result_is_frozen_dataclass() -> None:
    result = compute(
        is_rooted=False,
        is_emulator=False,
        is_new_device=True,
        geo_distance_km=0.0,
        hours_since_last_login=None,
    )
    assert isinstance(result, DeviceTrustResult)
    with pytest.raises((AttributeError, TypeError)):
        result.trust = 99.0  # type: ignore[misc]


# ── hours_since() ─────────────────────────────────────────────────────────────


def test_hours_since_recent() -> None:
    ts = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)).isoformat()
    result = hours_since(ts)
    assert result is not None
    assert abs(result - 2.0) < 0.01


def test_hours_since_none_input() -> None:
    assert hours_since(None) is None


def test_hours_since_empty_string() -> None:
    assert hours_since("") is None


def test_hours_since_invalid_string() -> None:
    assert hours_since("not-a-date") is None


def test_hours_since_bytes_input() -> None:
    ts = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=5)).isoformat()
    result = hours_since(ts.encode())
    assert result is not None
    assert abs(result - 5.0) < 0.01


def test_hours_since_naive_datetime() -> None:
    # Naive ISO string should be treated as UTC
    ts = dt.datetime.utcnow().isoformat()
    result = hours_since(ts)
    assert result is not None
    assert result < 0.1


# ── policy-driven budgets (Phase B4) ──────────────────────────────────────────


def test_custom_budgets_base_known_override() -> None:
    custom_budgets = {**_BUDGET_DEFAULTS, "base_known": 60.0}
    result = compute(
        is_rooted=False,
        is_emulator=False,
        is_new_device=False,
        geo_distance_km=0.0,
        hours_since_last_login=None,
        budgets=custom_budgets,
    )
    # With base_known=60 and no biometric, trust should be around 60
    assert result.trust == pytest.approx(60.0, abs=1.0)


def test_custom_budgets_rooted_ceiling_override() -> None:
    custom_budgets = {**_BUDGET_DEFAULTS, "rooted_ceiling": 5.0}
    result = compute(
        is_rooted=True,
        is_emulator=False,
        is_new_device=False,
        geo_distance_km=0.0,
        hours_since_last_login=None,
        budgets=custom_budgets,
    )
    assert result.trust == pytest.approx(5.0)
    assert result.device_class == "suspicious"


def test_custom_budgets_impossible_travel_threshold_override() -> None:
    # Lower impossible_travel_kmh so 500 km/h now counts as impossible travel
    custom_budgets = {**_BUDGET_DEFAULTS, "impossible_travel_kmh": 400.0}
    result = compute(
        is_rooted=False,
        is_emulator=False,
        is_new_device=False,
        geo_distance_km=500.0,
        hours_since_last_login=1.0,
        budgets=custom_budgets,
    )
    assert result.signals["impossible_travel"] is True


def test_default_budgets_none_matches_defaults() -> None:
    # Passing budgets=None should produce identical results to using _BUDGET_DEFAULTS
    result_none = compute(
        is_rooted=False,
        is_emulator=False,
        is_new_device=True,
        geo_distance_km=0.0,
        hours_since_last_login=None,
        budgets=None,
    )
    result_explicit = compute(
        is_rooted=False,
        is_emulator=False,
        is_new_device=True,
        geo_distance_km=0.0,
        hours_since_last_login=None,
        budgets=_BUDGET_DEFAULTS,
    )
    assert result_none.trust == result_explicit.trust
    assert result_none.device_class == result_explicit.device_class
