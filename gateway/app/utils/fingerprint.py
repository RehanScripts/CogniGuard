"""Device resolution: find-or-create `Device`/`UserDevice` rows from the signed
`BehaviorPayload.device` block (Implementation.md Phase 8). The fingerprint hash itself
is computed client-side (behavior-sdk, Phase 10) -- this module only resolves/persists
the server-side record for a fingerprint string that's already been HMAC-verified by
`integrity.py` before this is ever called.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..models.device import Device, UserDevice
from ..schemas.behavior import DeviceInfo


def get_or_create_device(db: DbSession, device_info: DeviceInfo) -> Device:
    device = db.scalar(select(Device).where(Device.device_fingerprint == device_info.fingerprint))
    if device is None:
        device = Device(
            device_fingerprint=device_info.fingerprint,
            os=device_info.platform,  # "web" | "android" -- no separate browser/app_version field on DeviceInfo
            browser=device_info.ua,
            is_rooted=device_info.is_rooted,
            is_emulator=device_info.is_emulator,
        )
        db.add(device)
        db.flush()
    else:
        device.last_seen_at = dt.datetime.now(dt.timezone.utc)
    return device


def get_or_create_user_device(
    db: DbSession, user_id: uuid.UUID, device_id: uuid.UUID
) -> UserDevice:
    user_device = db.scalar(
        select(UserDevice).where(UserDevice.user_id == user_id, UserDevice.device_id == device_id)
    )
    if user_device is None:
        user_device = UserDevice(
            user_id=user_id,
            device_id=device_id,
            trust_score=0,
            is_trusted=False,
            binding_status="pending",
        )
        db.add(user_device)
        db.flush()
    else:
        user_device.last_used_at = dt.datetime.now(dt.timezone.utc)
    return user_device
