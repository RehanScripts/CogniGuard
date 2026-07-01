"""Mobile distribution router (Implementation.md Phase 18) -- thin, delegates to
`services/mobile_distribution.py`. No ownership check on `ae-calib/{user_id}` (same
convention as `routers/risk.py`'s `GET /session/{id}`): calibration params are scale/
threshold/temperature floats, not PII, so this prototype doesn't ringfence the read
behind a session token.
"""

from __future__ import annotations

import base64
import os
import uuid

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.exceptions import InvalidSignature
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .. import deps
from ..models.device import UserDevice
from ..models.user import User
from ..models.session import Session as SessionModel
from ..schemas.mobile import AECalibrationOut, AEModelDistribution
from ..services import mobile_distribution

router = APIRouter()

_ENROLL_NONCE_TTL = 120  # seconds


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


# ── KeyStore biometric binding (Phase C3) ──────────────────────────────────────


class EnrollChallengeOut(BaseModel):
    enrollment_nonce: str
    device_id: str


class BindBiometricRequest(BaseModel):
    device_id: str
    enrollment_nonce: str
    public_key_pem: str
    signature_b64: str


class BindBiometricOut(BaseModel):
    device_id: str
    binding_status: str


@router.get("/device/enroll-challenge", response_model=EnrollChallengeOut)
def enroll_challenge(
    current: tuple[User, SessionModel] = Depends(deps.get_current_user),
    redis: Redis = Depends(deps.get_redis),
) -> EnrollChallengeOut:
    """Issue a server-side nonce for KeyStore-backed biometric enrollment (Phase C3).

    The Android client fetches this nonce, signs it with its StrongBox/TEE RSA private
    key, and submits the public key + signature to /device/bind-biometric.
    """
    _, session = current
    device_id = str(session.device_id) if session.device_id else "unknown"
    nonce = base64.urlsafe_b64encode(os.urandom(32)).decode()
    redis.set(f"enroll_nonce:{device_id}", nonce, ex=_ENROLL_NONCE_TTL)
    return EnrollChallengeOut(enrollment_nonce=nonce, device_id=device_id)


@router.post("/device/bind-biometric", response_model=BindBiometricOut)
def bind_biometric(
    req: BindBiometricRequest,
    current: tuple[User, SessionModel] = Depends(deps.get_current_user),
    db: DbSession = Depends(deps.get_db),
    redis: Redis = Depends(deps.get_redis),
) -> BindBiometricOut:
    """Bind an RSA public key to a device (Phase C3).

    Verifies:
    1. The enrollment nonce was issued by this server and hasn't been used.
    2. The signature is RSA-PKCS1v15-SHA256 over the nonce using the submitted key.
    """
    user, _ = current

    try:
        did = uuid.UUID(req.device_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid device_id")

    stored_nonce_raw = redis.get(f"enroll_nonce:{req.device_id}")
    if stored_nonce_raw is None:
        raise HTTPException(status_code=400, detail="enrollment nonce expired or not issued")

    stored_nonce = (
        stored_nonce_raw.decode() if isinstance(stored_nonce_raw, bytes) else stored_nonce_raw
    )
    if stored_nonce != req.enrollment_nonce:
        raise HTTPException(status_code=400, detail="enrollment nonce mismatch")

    # Consume nonce — single use only (CLAUDE.md invariant 11).
    redis.delete(f"enroll_nonce:{req.device_id}")

    try:
        public_key = serialization.load_pem_public_key(req.public_key_pem.encode())
        signature = base64.b64decode(req.signature_b64)
        public_key.verify(  # type: ignore[union-attr]
            signature,
            req.enrollment_nonce.encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except InvalidSignature:
        raise HTTPException(status_code=400, detail="signature verification failed")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"key/signature parse error: {exc}")

    link = db.scalar(
        select(UserDevice).where(
            UserDevice.user_id == user.user_id,
            UserDevice.device_id == did,
        )
    )
    if link is None:
        raise HTTPException(status_code=404, detail="device not linked to this user")

    link.public_key = req.public_key_pem
    link.is_trusted = True
    link.binding_status = "bound"
    db.commit()

    return BindBiometricOut(device_id=req.device_id, binding_status="bound")
