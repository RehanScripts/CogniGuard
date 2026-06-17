"""`TXN_HISTORY_UPI_FIN.csv` adapter (Implementation.md Phase 5).

UPI transaction log with no fraud label column, so we apply the PRD heuristic
(`is_new_payee AND amount_zscore > 2 AND odd_time` -> synthetic fraud). Per-payer
`amount_zscore`/`velocity_1h`/`velocity_24h`/`amount_sum_24h`/`is_new_payee` are computed
the same way the live system computes them (causally, from each payer's prior history
only) so the offline distribution matches what `feature_reader.read_bundle` produces
online. Re-imports the `odd_time`/new-payee-risk constants from the gateway's
feature_reader to keep train/serve parity exact (same container, same `app` package).
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from app.services.feature_reader import NEW_PAYEE_RISK, ODD_TIME_HOURS

EPS = 1e-9
_TS_FRACTION_TRIM = re.compile(r"(\.\d{6})\d+")
_TS_FORMAT = "%m-%d-%y %I:%M:%S.%f %p"


def _parse_ts(raw: pd.Series) -> pd.Series:
    trimmed = raw.str.replace(_TS_FRACTION_TRIM, r"\1", regex=True)
    return pd.to_datetime(trimmed, format=_TS_FORMAT, errors="coerce")


def load(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df["amount"] = pd.to_numeric(df["AMOUNT"], errors="coerce")
    df["ts"] = _parse_ts(df["TRN_DATE_TIME"])
    df["beneficiary_id"] = df["PAYEE_ADDRESS"].where(df["PAYEE_ADDRESS"] != "", df["PAYEE_ACCOUNT"])
    return df[df["PAYER_ACCOUNT"].ne("") & df["amount"].notna() & df["ts"].notna()]


def feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    """One row per transaction: amount, amount_zscore, velocity_1h/24h, amount_sum_24h,
    is_new_payee, beneficiary_risk, odd_time, and the heuristic fraud label — all
    computed causally (only from that payer's transactions strictly before `ts`)."""
    rows = []
    for payer, g in df.sort_values("ts").groupby("PAYER_ACCOUNT"):
        g = g.sort_values("ts").reset_index(drop=True)
        seen_beneficiaries: set[str] = set()
        amounts_so_far: list[float] = []
        for i, row in g.iterrows():
            prior = g.iloc[:i]
            prior_amounts = np.array(amounts_so_far)
            avg = float(prior_amounts.mean()) if len(prior_amounts) else 0.0
            std = float(prior_amounts.std(ddof=0)) if len(prior_amounts) else 0.0
            amount_zscore = (row["amount"] - avg) / max(std, EPS) if len(prior_amounts) else 0.0

            window_1h = prior[prior["ts"] > row["ts"] - pd.Timedelta(hours=1)]
            window_24h = prior[prior["ts"] > row["ts"] - pd.Timedelta(hours=24)]

            is_new_payee = row["beneficiary_id"] not in seen_beneficiaries
            beneficiary_risk = NEW_PAYEE_RISK if is_new_payee else 0.0
            odd_time = row["ts"].hour in ODD_TIME_HOURS

            rows.append(
                {
                    "payer_account": payer,
                    "transaction_id": row["TRANSACTION_ID"],
                    "ts": row["ts"],
                    "amount": row["amount"],
                    "amount_zscore": amount_zscore,
                    "velocity_1h": len(window_1h),
                    "velocity_24h": len(window_24h),
                    "amount_sum_24h": float(window_24h["amount"].sum()),
                    "is_new_payee": is_new_payee,
                    "beneficiary_risk": beneficiary_risk,
                    "odd_time": odd_time,
                    "label": int(is_new_payee and amount_zscore > 2 and odd_time),
                }
            )
            seen_beneficiaries.add(row["beneficiary_id"])
            amounts_so_far.append(row["amount"])
    return pd.DataFrame(rows)
