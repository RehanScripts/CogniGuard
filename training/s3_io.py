"""Parquet/joblib <-> S3 (MinIO) helpers shared by load_datasets.py and the training
scripts. Offline training is not on the inference hot path, so reusing the gateway's
`app.s3_client`/`app.db` here is fine — CLAUDE.md's "Redis only" rule is about scoring.
"""

from __future__ import annotations

import io
import os

import joblib
import pandas as pd

from app.config import settings
from app.s3_client import get_s3


def write_parquet(df: pd.DataFrame, key: str) -> str:
    buf = io.BytesIO()
    df.to_parquet(buf, engine="pyarrow", index=False)
    get_s3().put_object(Bucket=settings.s3_bucket, Key=key, Body=buf.getvalue())
    return f"s3://{settings.s3_bucket}/{key}"


def read_parquet(key: str) -> pd.DataFrame:
    body = get_s3().get_object(Bucket=settings.s3_bucket, Key=key)["Body"].read()
    return pd.read_parquet(io.BytesIO(body), engine="pyarrow")


def write_joblib(obj, key: str, *, local_path: str | None = None) -> str:
    buf = io.BytesIO()
    joblib.dump(obj, buf)
    data = buf.getvalue()
    get_s3().put_object(Bucket=settings.s3_bucket, Key=key, Body=data)
    if local_path:
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(data)
    return f"s3://{settings.s3_bucket}/{key}"
