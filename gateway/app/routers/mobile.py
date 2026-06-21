"""Mobile distribution router (Implementation.md Phase 18) -- thin, delegates to
`services/mobile_distribution.py`. No ownership check on `ae-calib/{user_id}` (same
convention as `routers/risk.py`'s `GET /session/{id}`): calibration params are scale/
threshold/temperature floats, not PII, so this prototype doesn't ringfence the read
behind a session token.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from redis import Redis
from sqlalchemy.orm import Session as DbSession

from .. import deps
from ..schemas.mobile import AECalibrationOut, AEModelDistribution
from ..services import mobile_distribution

router = APIRouter()


@router.get("/ae-model", response_model=AEModelDistribution)
def get_ae_model(db: DbSession = Depends(deps.get_db)) -> AEModelDistribution:
    try:
        dist = mobile_distribution.resolve_model(db)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return AEModelDistribution(
        version=dist.version, download_url=dist.download_url, expires_in_s=dist.expires_in_s
    )


@router.get("/ae-calib/{user_id}", response_model=AECalibrationOut)
def get_ae_calib(user_id: str, redis: Redis = Depends(deps.get_redis)) -> AECalibrationOut:
    params = mobile_distribution.resolve_calibration(user_id, redis=redis)
    return AECalibrationOut(
        scale=params.scale, threshold=params.threshold, temperature=params.temperature
    )
