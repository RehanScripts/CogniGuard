"""Mobile distribution response contracts (Implementation.md Phase 18)."""

from __future__ import annotations

from pydantic import BaseModel


class AEModelDistribution(BaseModel):
    version: str
    download_url: str  # presigned S3/MinIO GET URL for the .tflite artifact
    expires_in_s: int


class AECalibrationOut(BaseModel):
    scale: float
    threshold: float
    temperature: float
