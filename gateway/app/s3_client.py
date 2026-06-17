from functools import lru_cache

import boto3
from botocore.client import BaseClient, Config

from .config import settings


@lru_cache(maxsize=1)
def get_s3() -> BaseClient:
    """S3 client pointed at MinIO (data lake + model store)."""
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def ping() -> bool:
    """Return True if the configured bucket is reachable."""
    try:
        get_s3().head_bucket(Bucket=settings.s3_bucket)
        return True
    except Exception:
        return False
