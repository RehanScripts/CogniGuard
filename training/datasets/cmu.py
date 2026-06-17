"""CMU `DSL-StrongPasswordData.csv` adapter (Implementation.md Phase 5).

51 subjects x 400 repetitions typing the fixed password ".tie5Roanl" + Return (11
keystrokes). Columns are `H.<key>` (hold/dwell time), `DD.<a>.<b>` (down-down digraph
latency), `UD.<a>.<b>` (up-down / flight latency) — all in seconds. Reduces each row to
the 4 typing-relevant dimensions of the shared `BehaviorFeatures` vector (Architecture
§5.2) so it can be pooled with HMOG's touch/motion dimensions for the global IF prior.
"""

from __future__ import annotations

import pandas as pd

ID_COLUMNS = ["subject", "sessionIndex", "rep"]


def load(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


def behavior_frame(df: pd.DataFrame) -> pd.DataFrame:
    """subject/session id columns + typing_speed, key_latency_avg, typing_rhythm_std,
    hold_time_avg — the typing-relevant slice of BehaviorFeatures. Touch/motion/mouse
    dims are out of scope for a keyboard-only dataset; callers default those to 0.0."""
    h_cols = [c for c in df.columns if c.startswith("H.")]
    dd_cols = [c for c in df.columns if c.startswith("DD.")]
    ud_cols = [c for c in df.columns if c.startswith("UD.")]
    n_keys = len(h_cols)

    total_time_s = df[dd_cols].sum(axis=1) + df["H.Return"]
    out = df[ID_COLUMNS].copy()
    out["typing_speed"] = n_keys / total_time_s.replace(0, pd.NA)
    out["key_latency_avg"] = df[ud_cols].mean(axis=1)
    out["typing_rhythm_std"] = df[ud_cols].std(axis=1, ddof=0)
    out["hold_time_avg"] = df[h_cols].mean(axis=1)
    return out.fillna({"typing_speed": 0.0})
