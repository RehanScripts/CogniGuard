"""Dev-only helper endpoints — mounted only when app_env == 'dev'.

These endpoints expose internal state (Redis OTPs, seeded challenge IDs) that
must NEVER be reachable in staging or production.  The router is conditionally
mounted in main.py; if app_env != 'dev' the module isn't imported.
"""

from fastapi import APIRouter, HTTPException
from ..redis_client import redis_client
from ..config import settings

router = APIRouter()


@router.get("/otp/{challenge_id}", summary="[DEV] Read OTP from Redis")
def get_dev_otp(challenge_id: str) -> dict:
    """Return the current OTP stored in Redis for *challenge_id*.

    Only works when app_env == 'dev'.  Use this during demos when SMTP is not
    configured — copy the code from this response and paste it into the app.
    """
    if settings.app_env != "dev":
        raise HTTPException(status_code=404, detail="Not found")
    raw = redis_client.get(f"otp:{challenge_id}")
    if raw is None:
        raise HTTPException(status_code=404, detail="OTP not found or already used")
    code = raw.decode() if isinstance(raw, bytes) else raw
    return {"challenge_id": challenge_id, "otp": code}
