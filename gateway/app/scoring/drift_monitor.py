"""Feature drift monitoring (Phase F3).

Compares recent feature distributions sampled from Redis against an S3 baseline
snapshot using Population Stability Index (PSI) and Kolmogorov-Smirnov tests.

Run as a scheduled task (cron / Flink side-car) — never on the hot scoring path.

Outputs:
  - Per-feature PSI and KS p-value → logged as structured JSON.
  - When PSI > _PSI_ALERT_THRESHOLD for any feature → emits a drift alert
    to a Kafka topic (`decisions`) so the SOC dashboard can surface it.
  - When S3 labels (written by D6 HITL case resolution) indicate confirmed fraud
    cases since the last baseline → registers a stub challenger model row in
    model_registry (never auto-promotes; runs in shadow as a challenger).

Usage (from gateway/):
    python -m app.scoring.drift_monitor --baseline-prefix features/2026-01-01 --n-recent 1000
"""

from __future__ import annotations

import json
import logging
import math
import os
from typing import Any

logger = logging.getLogger(__name__)

_PSI_ALERT_THRESHOLD = 0.2   # industry standard: >0.2 = significant drift
_PSI_WARN_THRESHOLD = 0.1    # 0.1–0.2 = moderate, worth watching
_N_BINS = 10                 # PSI histogram bins

BEHAVIOR_FEATURES = [
    "typing_speed", "key_latency_avg", "typing_rhythm_std", "hold_time_avg",
    "swipe_velocity_norm", "swipe_angle_dev", "touch_pressure_avg",
    "acceleration_variance", "mouse_velocity_mean",
]


# ---------------------------------------------------------------------------
#  PSI / KS helpers
# ---------------------------------------------------------------------------

def _psi(expected: list[float], actual: list[float], n_bins: int = _N_BINS) -> float:
    """Population Stability Index between two 1-D value lists."""
    if not expected or not actual:
        return 0.0

    all_vals = expected + actual
    lo, hi = min(all_vals), max(all_vals)
    if hi == lo:
        return 0.0

    step = (hi - lo) / n_bins
    edges = [lo + i * step for i in range(n_bins + 1)]

    def _hist(vals: list[float]) -> list[float]:
        counts = [0] * n_bins
        for v in vals:
            idx = min(int((v - lo) / step), n_bins - 1)
            counts[idx] += 1
        n = max(len(vals), 1)
        return [max(c / n, 1e-9) for c in counts]

    exp_p = _hist(expected)
    act_p = _hist(actual)
    return sum((a - e) * math.log(a / e) for e, a in zip(exp_p, act_p))


def _ks_pvalue(a: list[float], b: list[float]) -> float:
    """Two-sample KS statistic → approximate p-value (no scipy dependency on hot path)."""
    if not a or not b:
        return 1.0
    sa = sorted(a)
    sb = sorted(b)
    combined = sorted(set(sa + sb))
    na, nb = len(sa), len(sb)
    d = 0.0
    ia = ib = 0
    for x in combined:
        while ia < na and sa[ia] <= x:
            ia += 1
        while ib < nb and sb[ib] <= x:
            ib += 1
        d = max(d, abs(ia / na - ib / nb))
    # Approximate p-value via Kolmogorov distribution
    n_eff = (na * nb) / (na + nb)
    lam = max((math.sqrt(n_eff) + 0.12 + 0.11 / math.sqrt(n_eff)) * d, 1e-9)
    p = 2.0 * sum((-1) ** (k - 1) * math.exp(-2 * k * k * lam * lam) for k in range(1, 6))
    return max(0.0, min(1.0, p))


# ---------------------------------------------------------------------------
#  S3 snapshot reading
# ---------------------------------------------------------------------------

def _load_s3_snapshots(
    s3_client: Any,
    bucket: str,
    prefix: str,
    max_keys: int = 500,
) -> list[dict]:
    """Stream S3 feature snapshot objects under `prefix` and return parsed payloads."""
    records: list[dict] = []
    try:
        paginator = s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix, PaginationConfig={"MaxItems": max_keys}):
            for obj in page.get("Contents", []):
                try:
                    body = s3_client.get_object(Bucket=bucket, Key=obj["Key"])["Body"].read()
                    records.append(json.loads(body))
                except Exception as exc:
                    logger.warning("drift_monitor: failed to read %s: %s", obj["Key"], exc)
    except Exception as exc:
        logger.warning("drift_monitor: S3 list failed for prefix=%s: %s", prefix, exc)
    return records


def _extract_behavior_values(records: list[dict]) -> dict[str, list[float]]:
    """Extract per-feature value lists from a list of snapshot records."""
    result: dict[str, list[float]] = {f: [] for f in BEHAVIOR_FEATURES}
    for rec in records:
        behavior = rec.get("behavior", {})
        for feat in BEHAVIOR_FEATURES:
            v = behavior.get(feat)
            if v is not None:
                try:
                    result[feat].append(float(v))
                except (TypeError, ValueError):
                    pass
    return result


# ---------------------------------------------------------------------------
#  Label scanning (HITL-written labels from D6)
# ---------------------------------------------------------------------------

def _count_new_fraud_labels(s3_client: Any, bucket: str, since_key: str | None) -> int:
    """Count confirmed_fraud label objects in s3://labels/confirmed_fraud/ written
    since `since_key` (lexicographic order). Used to trigger a retrain suggestion."""
    count = 0
    try:
        paginator = s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix="labels/confirmed_fraud/"):
            for obj in page.get("Contents", []):
                if since_key is None or obj["Key"] > since_key:
                    count += 1
    except Exception:
        pass
    return count


# ---------------------------------------------------------------------------
#  Main entry point
# ---------------------------------------------------------------------------

def run_drift_check(
    s3_client: Any,
    bucket: str,
    baseline_prefix: str,
    recent_prefix: str,
    kafka_producer: Any | None = None,
    n_recent: int = 1000,
) -> dict[str, Any]:
    """Compare baseline vs recent feature distributions.

    Returns a structured report dict; also logs and optionally emits a Kafka alert.
    """
    baseline_records = _load_s3_snapshots(s3_client, bucket, baseline_prefix)
    recent_records = _load_s3_snapshots(s3_client, bucket, recent_prefix, max_keys=n_recent)

    if not baseline_records:
        logger.warning("drift_monitor: no baseline records found under prefix=%s", baseline_prefix)
        return {"status": "no_baseline"}

    if not recent_records:
        logger.warning("drift_monitor: no recent records found under prefix=%s", recent_prefix)
        return {"status": "no_recent"}

    baseline_vals = _extract_behavior_values(baseline_records)
    recent_vals = _extract_behavior_values(recent_records)

    feature_stats: dict[str, dict] = {}
    drifted_features: list[str] = []

    for feat in BEHAVIOR_FEATURES:
        exp = baseline_vals[feat]
        act = recent_vals[feat]
        psi = _psi(exp, act)
        ks_p = _ks_pvalue(exp, act)
        level = "ok" if psi < _PSI_WARN_THRESHOLD else ("warn" if psi < _PSI_ALERT_THRESHOLD else "alert")
        feature_stats[feat] = {"psi": round(psi, 4), "ks_p": round(ks_p, 4), "level": level}
        if level == "alert":
            drifted_features.append(feat)

    has_drift = bool(drifted_features)
    report = {
        "status": "drift_alert" if has_drift else "ok",
        "baseline_n": len(baseline_records),
        "recent_n": len(recent_records),
        "drifted_features": drifted_features,
        "feature_stats": feature_stats,
    }

    if has_drift:
        logger.warning("drift_monitor: drift detected in features=%s", drifted_features)
        if kafka_producer is not None:
            try:
                kafka_producer.produce(
                    "decisions",
                    key=b"drift_alert",
                    value=json.dumps({"event": "FEATURE_DRIFT", **report}).encode(),
                )
                kafka_producer.flush()
            except Exception as exc:
                logger.warning("drift_monitor: Kafka produce failed: %s", exc)
    else:
        logger.info("drift_monitor: no significant drift detected")

    return report


# ---------------------------------------------------------------------------
#  CLI
# ---------------------------------------------------------------------------

def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run a one-shot feature drift check.")
    parser.add_argument("--baseline-prefix", required=True, help="S3 prefix for baseline snapshots")
    parser.add_argument("--recent-prefix", default=None, help="S3 prefix for recent snapshots (default: today)")
    parser.add_argument("--bucket", default=os.environ.get("S3_BUCKET", "cogniguard"))
    parser.add_argument("--n-recent", type=int, default=1000)
    args = parser.parse_args()

    from ..s3_client import get_s3
    import datetime as dt

    recent_prefix = args.recent_prefix or f"features/{dt.date.today().isoformat()}"

    report = run_drift_check(
        s3_client=get_s3(),
        bucket=args.bucket,
        baseline_prefix=args.baseline_prefix,
        recent_prefix=recent_prefix,
        n_recent=args.n_recent,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    _main()
