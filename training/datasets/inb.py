"""`INB_REQ_LOG.csv` adapter (Implementation.md Phase 5).

`INB_REQUEST`/`INB_RESPONSE` are packed fixed-width mainframe records whose layout
differs per `INB_SERVICE_ID` and isn't documented anywhere in this repo — decoding them
would mean guessing at undocumented offsets, so we don't. None of the PRD §6.6 session
features actually need them: `session_duration`, `request_velocity`, `nav_entropy`,
`odd_time`, and `beneficiary_add_to_pay_gap` are all derivable from the structured
columns (`INB_USER_ID`, `INB_SESSION_ID`, `INB_HANDLE_ID`, `INB_SERVICE_ID`,
`INB_REQUEST_DATE`) grouped per session. The packed fields are kept opaque.

`INB_HANDLE_ID` carries the screen/transaction marker per request — `201_RTGS` = add
beneficiary, `203_RTGS` = execute transfer (PRD §6.6's primary coercion signal: how long
between adding a payee and paying them).
"""

from __future__ import annotations

import math
import re
from collections import Counter

import pandas as pd

_TS_FORMAT = "%Y-%m-%d-%H.%M.%S.%f"
_TXN_HANDLE_PATTERN = r"TXDN|RTGS|ONLINEPAY|BILLPAY"


def load(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df["INB_REQUEST_DATE"] = pd.to_datetime(df["INB_REQUEST_DATE"], format=_TS_FORMAT, errors="coerce")
    return df[(df["INB_SESSION_ID"] != "") & df["INB_REQUEST_DATE"].notna()]


def _shannon_entropy(labels: list[str]) -> float:
    n = len(labels)
    if n == 0:
        return 0.0
    counts = Counter(labels)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def session_features(df: pd.DataFrame, *, odd_time_hours: frozenset[int]) -> pd.DataFrame:
    """One row per (user, session): session_duration, request_velocity, nav_entropy,
    odd_time, beneficiary_add_to_pay_gap, pre_txn_dwell."""
    rows = []
    for (user_id, session_id), g in df.sort_values("INB_REQUEST_DATE").groupby(
        ["INB_USER_ID", "INB_SESSION_ID"]
    ):
        ts = g["INB_REQUEST_DATE"]
        handles = g["INB_HANDLE_ID"].astype(str)
        session_duration = (ts.iloc[-1] - ts.iloc[0]).total_seconds()
        request_velocity = len(g) / max(session_duration, 1.0)
        nav_entropy = _shannon_entropy(g["INB_SERVICE_ID"].tolist())
        odd_time = ts.iloc[0].hour in odd_time_hours

        add_ts = ts[handles.str.contains("201_RTGS", na=False)]
        pay_ts = ts[handles.str.contains("203_RTGS", na=False)]
        beneficiary_add_to_pay_gap = None
        if not add_ts.empty and not pay_ts.empty:
            gap_min = (pay_ts.min() - add_ts.min()).total_seconds() / 60.0
            beneficiary_add_to_pay_gap = gap_min if gap_min >= 0 else None

        txn_pattern = re.compile(_TXN_HANDLE_PATTERN)
        txn_positions = [i for i, h in enumerate(handles) if txn_pattern.search(h)]
        pre_txn_dwell = None
        if txn_positions and txn_positions[0] > 0:
            pos = txn_positions[0]
            pre_txn_dwell = (ts.iloc[pos] - ts.iloc[pos - 1]).total_seconds()

        rows.append(
            {
                "user_id": user_id,
                "session_id": session_id,
                "session_duration": session_duration,
                "request_velocity": request_velocity,
                "nav_entropy": nav_entropy,
                "odd_time": odd_time,
                "beneficiary_add_to_pay_gap": beneficiary_add_to_pay_gap,
                "pre_txn_dwell": pre_txn_dwell,
                "request_count": len(g),
            }
        )
    return pd.DataFrame(rows)
