"""Customer banking read schemas (Phase 28, authorized exception) -- thin, read-only
over existing Account/Transaction/Beneficiary/User models. PII is masked at the service
layer before these are constructed. No security telemetry (scores/bands/model names)
belongs here -- the customer/SOC split applies from this wire contract on, not deferred
to the Phase 29/30 UI layer."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel


class ProfileOut(BaseModel):
    user_id: str
    customer_ref: str | None = None
    full_name: str | None = None
    masked_email: str | None = None
    masked_phone: str | None = None
    kyc_level: str | None = None
    account_status: str
    member_since: dt.datetime | None = None


class AccountOut(BaseModel):
    account_id: str
    masked_account_number: str | None = None
    account_type: str | None = None
    balance: float | None = None
    currency: str | None = None
    status: str | None = None
    opened_at: dt.datetime | None = None


class TransactionOut(BaseModel):
    transaction_id: str
    account_id: str | None = None
    beneficiary_name: str | None = None
    masked_beneficiary_account: str | None = None
    amount: float | None = None
    currency: str | None = None
    transfer_type: str | None = None
    channel: str | None = None
    status: str | None = None
    initiated_at: dt.datetime | None = None
    completed_at: dt.datetime | None = None


class BeneficiaryOut(BaseModel):
    beneficiary_id: str
    name: str | None = None
    masked_account_number: str | None = None
    bank_code: str | None = None
    beneficiary_type: str | None = None
    is_verified: bool
    transfer_count: int
    added_at: dt.datetime | None = None


class TrustedDeviceOut(BaseModel):
    device_id: str
    label: str | None = None
    is_trusted: bool
    last_used_at: dt.datetime | None = None


class ActiveSessionOut(BaseModel):
    session_id: str
    device_label: str | None = None
    location: str | None = None
    started_at: dt.datetime | None = None


class SecuritySettingsOut(BaseModel):
    trusted_devices: list[TrustedDeviceOut]
    active_sessions: list[ActiveSessionOut]
