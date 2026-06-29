"""Real OTP generation, Redis-backed verification, and SMTP delivery (Phase C1).

Redis keys:
  otp:{challenge_id}   — 6-digit code, TTL from policy (default 300 s), consumed on success.

Email is sent via stdlib smtplib in a background thread (called as BackgroundTask).
If smtp_host is empty (dev default), sending is skipped silently so the flow still works
without SMTP configured — the OTP code is still generated in Redis and verifiable.
"""

from __future__ import annotations

import secrets
import smtplib
import logging
from email.mime.text import MIMEText

from redis import Redis

from ..config import settings

logger = logging.getLogger(__name__)

_OTP_LENGTH = 6
_OTP_TTL_S = 300  # 5 minutes; policy override not wired yet


def generate_otp(challenge_id: str, redis: Redis, *, ttl: int = _OTP_TTL_S) -> str:
    """Generate a cryptographically random 6-digit OTP, store in Redis, return the code."""
    code = "".join(secrets.choice("0123456789") for _ in range(_OTP_LENGTH))
    redis.set(f"otp:{challenge_id}", code, ex=ttl)
    return code


def verify_otp(challenge_id: str, code: str, redis: Redis) -> bool:
    """Compare *code* against the stored OTP; consume (delete) the key on success."""
    stored_raw = redis.get(f"otp:{challenge_id}")
    if stored_raw is None:
        return False
    stored = stored_raw.decode() if isinstance(stored_raw, bytes) else stored_raw
    if stored != code:
        return False
    redis.delete(f"otp:{challenge_id}")
    return True


def send_otp_email(to_email: str, code: str) -> None:
    """Send the OTP to *to_email* via SMTP.  Runs in a background thread.

    No-ops when smtp_host is empty or to_email is blank — the OTP is still
    verifiable via Redis for environments without an SMTP relay configured.
    """
    if not settings.smtp_host or not to_email:
        if not settings.smtp_host:
            logger.debug("SMTP not configured; OTP %s skipped for %s", code, to_email)
        return

    msg = MIMEText(
        f"Your Central Bank of India one-time password is:\n\n"
        f"    {code}\n\n"
        f"It expires in 5 minutes. Do not share it with anyone.\n\n"
        f"If you did not request this code, contact Central Bank of India immediately."
    )
    msg["Subject"] = "Central Bank of India — One-Time Password"
    msg["From"] = settings.smtp_from_email
    msg["To"] = to_email

    try:
        # Gmail App Passwords are displayed with spaces for readability but must be
        # sent without spaces to the SMTP server.
        smtp_password = settings.smtp_password.replace(" ", "")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as s:
            s.ehlo()
            if s.has_extn("STARTTLS"):
                s.starttls()
                s.ehlo()
            if settings.smtp_username:
                s.login(settings.smtp_username, smtp_password)
            s.sendmail(settings.smtp_from_email, [to_email], msg.as_string())
        logger.info("OTP email sent to %s for challenge", to_email)
    except Exception:
        logger.exception("Failed to send OTP email to %s", to_email)
