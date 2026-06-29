"""pytest coverage for benchmark metric helpers (UPGRADE_PLAN Phase A3).

Tests metric correctness on tiny synthetic datasets — no S3, Redis, Postgres, or
TensorFlow required. The functions under test are pure numpy/sklearn utilities
exposed by benchmark.py.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from training.benchmark import (
    binary_metrics_at_eer,
    eer_from_scores,
    latency_stats,
    run_track2,
)


# ---------------------------------------------------------------------------
# eer_from_scores
# ---------------------------------------------------------------------------

def test_eer_perfect_separation():
    """When genuine and impostor are perfectly separated the EER should be 0.

    Convention: higher score = more anomalous = impostor.
    Genuine users should have LOW anomaly scores; impostors should have HIGH.
    """
    genuine = np.array([0.1, 0.2, 0.15, 0.05])   # low anomaly = genuine
    impostor = np.array([0.9, 0.85, 0.95, 1.0])  # high anomaly = impostor
    assert eer_from_scores(genuine, impostor) == pytest.approx(0.0, abs=1e-6)


def test_eer_complete_overlap():
    """When distributions are identical the EER should be 0.5."""
    scores = np.array([0.3, 0.5, 0.7, 0.2, 0.8])
    eer = eer_from_scores(scores, scores)
    assert eer == pytest.approx(0.5, abs=0.05)


def test_eer_in_unit_interval():
    rng = np.random.default_rng(0)
    genuine = rng.normal(0.3, 0.1, 200)   # lower anomaly scores
    impostor = rng.normal(0.7, 0.1, 200)  # higher anomaly scores
    eer = eer_from_scores(genuine, impostor)
    assert 0.0 <= eer <= 1.0


def test_eer_symmetry():
    """Negating all scores and swapping genuine/impostor leaves EER unchanged.

    original: genuine ~ N(0.3), impostor ~ N(0.7), convention: higher = impostor
    flipped:  genuine = -N(0.7) ~ N(-0.7), impostor = -N(0.3) ~ N(-0.3),
              convention still holds (N(-0.7) < N(-0.3), so flipped-genuine is lower)
    """
    rng = np.random.default_rng(1)
    genuine = rng.normal(0.3, 0.1, 100)
    impostor = rng.normal(0.7, 0.1, 100)
    eer_forward = eer_from_scores(genuine, impostor)
    eer_flipped = eer_from_scores(-impostor, -genuine)
    assert eer_forward == pytest.approx(eer_flipped, abs=0.05)


# ---------------------------------------------------------------------------
# binary_metrics_at_eer
# ---------------------------------------------------------------------------

def test_binary_metrics_keys():
    rng = np.random.default_rng(2)
    genuine = rng.normal(0.3, 0.1, 50)
    impostor = rng.normal(0.7, 0.1, 50)
    result = binary_metrics_at_eer(genuine, impostor)
    for key in ("eer", "far", "frr", "roc_auc", "pr_auc", "accuracy", "precision", "recall", "f1", "threshold"):
        assert key in result, f"missing key: {key}"


def test_binary_metrics_ranges():
    rng = np.random.default_rng(3)
    genuine = rng.normal(0.3, 0.15, 100)
    impostor = rng.normal(0.7, 0.15, 100)
    m = binary_metrics_at_eer(genuine, impostor)
    for k in ("eer", "far", "frr", "accuracy", "precision", "recall", "f1"):
        assert 0.0 <= m[k] <= 1.0, f"{k}={m[k]} out of [0,1]"
    assert 0.0 <= m["roc_auc"] <= 1.0
    assert 0.0 <= m["pr_auc"] <= 1.0


def test_binary_metrics_perfect_separation():
    genuine = np.array([0.1, 0.2, 0.05])
    impostor = np.array([0.9, 0.95, 0.85])
    m = binary_metrics_at_eer(genuine, impostor)
    assert m["eer"] == pytest.approx(0.0, abs=1e-6)
    assert m["roc_auc"] == pytest.approx(1.0, abs=1e-6)


def test_binary_metrics_eer_consistent():
    """EER field in the bundle should match eer_from_scores independently."""
    rng = np.random.default_rng(4)
    genuine = rng.normal(0.4, 0.12, 200)
    impostor = rng.normal(0.6, 0.12, 200)
    m = binary_metrics_at_eer(genuine, impostor)
    standalone = eer_from_scores(genuine, impostor)
    assert m["eer"] == pytest.approx(standalone, abs=1e-9)


# ---------------------------------------------------------------------------
# latency_stats
# ---------------------------------------------------------------------------

def test_latency_stats_keys():
    def identity(x):
        return x

    single = np.ones((1, 4))
    batch = np.ones((100, 4))
    stats = latency_stats(identity, single, batch, n_reps=5)
    for key in ("single_p50_ms", "single_p95_ms", "batch_p50_ms", "batch_p95_ms"):
        assert key in stats
        assert stats[key] >= 0.0


def test_latency_p95_ge_p50():
    def slow_fn(x):
        return x * 2.0

    single = np.zeros((1, 9))
    batch = np.zeros((50, 9))
    stats = latency_stats(slow_fn, single, batch, n_reps=10)
    assert stats["single_p95_ms"] >= stats["single_p50_ms"]
    assert stats["batch_p95_ms"] >= stats["batch_p50_ms"]


# ---------------------------------------------------------------------------
# run_track2 — synthetic data
# ---------------------------------------------------------------------------

def _synthetic_txn_df(n: int = 200, seed: int = 42) -> "pd.DataFrame":
    import pandas as pd
    rng = np.random.default_rng(seed)
    n_pos = max(6, n // 5)
    n_neg = n - n_pos
    labels = np.array([0] * n_neg + [1] * n_pos)
    rng.shuffle(labels)
    df = pd.DataFrame({
        "amount": rng.uniform(100, 50000, n),
        "amount_zscore": rng.standard_normal(n),
        "velocity_1h": rng.integers(0, 10, n).astype(float),
        "velocity_24h": rng.integers(0, 50, n).astype(float),
        "amount_sum_24h": rng.uniform(0, 500000, n),
        "is_new_payee": rng.integers(0, 2, n).astype(float),
        "beneficiary_risk": rng.uniform(0, 1, n),
        "odd_time": rng.integers(0, 2, n).astype(float),
        "behavior_score": rng.uniform(0, 1, n),
        "label": labels,
    })
    return df


def test_run_track2_returns_results():
    df = _synthetic_txn_df(300)
    results = run_track2(df, seed=0)
    assert len(results) >= 1
    for r in results:
        assert "model" in r
        assert "roc_auc" in r or "error" in r


def test_run_track2_metric_ranges():
    df = _synthetic_txn_df(300)
    results = run_track2(df, seed=0)
    for r in results:
        if "error" in r:
            continue
        for key in ("roc_auc", "pr_auc"):
            val = r[key]
            assert math.isnan(val) or 0.0 <= val <= 1.0, f"{r['model']}.{key}={val}"


def test_run_track2_latency_present():
    df = _synthetic_txn_df(300)
    results = run_track2(df, seed=0)
    for r in results:
        if "error" in r:
            continue
        assert "single_p50_ms" in r
        assert r["single_p95_ms"] >= 0.0
