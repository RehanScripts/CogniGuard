"""Load CMU/HMOG/INB_REQ_LOG/TXN_HISTORY_UPI_FIN into S3 parquet partitions
(Implementation.md Phase 5). Runnable standalone:  python -m scripts.load_datasets
"""

from __future__ import annotations

import logging
import os

from app.services.feature_reader import ODD_TIME_HOURS
from training.datasets import cmu, hmog, inb, txn
from training.s3_io import write_parquet

logger = logging.getLogger("cogniguard.load_datasets")

SAMPLE_DATA_DIR = os.environ.get("SAMPLE_DATA_DIR", "/data/sample")
PREFIX = "training"


def _path(filename: str) -> str:
    return os.path.join(SAMPLE_DATA_DIR, filename)


def load_cmu() -> str:
    df = cmu.behavior_frame(cmu.load(_path("DSL-StrongPasswordData.csv")))
    return write_parquet(df, f"{PREFIX}/cmu/behavior.parquet")


def load_hmog() -> str:
    cleaned = hmog.clean(hmog.load(_path("hmog_features.csv")))
    return write_parquet(cleaned, f"{PREFIX}/hmog/behavior.parquet")


def load_inb() -> str:
    sessions = inb.session_features(
        inb.load(_path("INB_REQ_LOG.csv")), odd_time_hours=ODD_TIME_HOURS
    )
    return write_parquet(sessions, f"{PREFIX}/inb/sessions.parquet")


def load_txn() -> str:
    features = txn.feature_frame(txn.load(_path("TXN_HISTORY_UPI_FIN.csv")))
    return write_parquet(features, f"{PREFIX}/txn/transactions.parquet")


def load_all() -> dict[str, str]:
    loaders = {"cmu": load_cmu, "hmog": load_hmog, "inb": load_inb, "txn": load_txn}
    written = {}
    for name, loader in loaders.items():
        uri = loader()
        written[name] = uri
        logger.info("wrote %s -> %s", name, uri)
    return written


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    for name, uri in load_all().items():
        print(f"{name}: {uri}")
