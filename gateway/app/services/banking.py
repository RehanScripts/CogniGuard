"""Banking read-path logic (Phase 28, authorized exception) -- thin SQLAlchemy 2.x
`select()` queries over existing models, PII masked before leaving this layer. The
customer banking screens (Accounts/Transactions/Beneficiaries/Profile/Security Settings)
had no existing read API, only ORM models with zero routes; this is the one approved
exception to "no new backend functionality" -- read-only, no new tables/writes/scoring.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..models.beneficiary import Beneficiary, UserBeneficiary
from ..models.device import Device, UserDevice
from ..models.session import Session as SessionModel
from ..models.transaction import Transaction
from ..models.user import Account, User
from ..schemas.banking import (
    AccountOut,
    ActiveSessionOut,
    BeneficiaryOut,
    ProfileOut,
    SecuritySettingsOut,
    TransactionOut,
    TrustedDeviceOut,
)
from ..utils.mask import mask_account_number, mask_email, mask_phone


def get_profile(user: User) -> ProfileOut:
    return ProfileOut(
        user_id=str(user.user_id),
        customer_ref=user.customer_ref,
        full_name=user.full_name,
        masked_email=mask_email(user.email),
        masked_phone=mask_phone(user.phone),
        kyc_level=user.kyc_level,
        account_status=user.account_status,
        member_since=user.created_at,
    )


def list_accounts(db: DbSession, user: User) -> list[AccountOut]:
    rows = db.scalars(select(Account).where(Account.user_id == user.user_id)).all()
    return [
        AccountOut(
            account_id=str(a.account_id),
            masked_account_number=mask_account_number(a.account_number),
            account_type=a.account_type,
            balance=float(a.balance) if a.balance is not None else None,
            currency=a.currency,
            status=a.status,
            opened_at=a.opened_at,
        )
        for a in rows
    ]


def list_transactions(db: DbSession, user: User, *, limit: int = 50) -> list[TransactionOut]:
    stmt = (
        select(Transaction, Beneficiary)
        .outerjoin(Beneficiary, Transaction.beneficiary_id == Beneficiary.beneficiary_id)
        .where(Transaction.user_id == user.user_id)
        .order_by(Transaction.initiated_at.desc())
        .limit(limit)
    )
    return [
        TransactionOut(
            transaction_id=str(txn.transaction_id),
            account_id=str(txn.account_id) if txn.account_id else None,
            beneficiary_name=beneficiary.name if beneficiary else None,
            masked_beneficiary_account=(
                mask_account_number(beneficiary.account_number) if beneficiary else None
            ),
            amount=float(txn.amount) if txn.amount is not None else None,
            currency=txn.currency,
            transfer_type=txn.transfer_type,
            channel=txn.channel,
            status=txn.status,
            initiated_at=txn.initiated_at,
            completed_at=txn.completed_at,
        )
        for txn, beneficiary in db.execute(stmt).all()
    ]


def list_beneficiaries(db: DbSession, user: User) -> list[BeneficiaryOut]:
    stmt = (
        select(UserBeneficiary, Beneficiary)
        .join(Beneficiary, UserBeneficiary.beneficiary_id == Beneficiary.beneficiary_id)
        .where(UserBeneficiary.user_id == user.user_id)
        .order_by(UserBeneficiary.added_at.desc())
    )
    return [
        BeneficiaryOut(
            beneficiary_id=str(beneficiary.beneficiary_id),
            name=beneficiary.name,
            masked_account_number=mask_account_number(beneficiary.account_number),
            bank_code=beneficiary.bank_code,
            beneficiary_type=beneficiary.beneficiary_type,
            is_verified=link.is_verified,
            transfer_count=link.transfer_count,
            added_at=link.added_at,
        )
        for link, beneficiary in db.execute(stmt).all()
    ]


def get_security_settings(db: DbSession, user: User) -> SecuritySettingsOut:
    device_stmt = (
        select(UserDevice, Device)
        .join(Device, UserDevice.device_id == Device.device_id)
        .where(UserDevice.user_id == user.user_id)
        .order_by(UserDevice.last_used_at.desc())
    )
    trusted_devices = [
        TrustedDeviceOut(
            device_id=str(device.device_id),
            label=" ".join(p for p in (device.os, device.browser) if p) or None,
            is_trusted=link.is_trusted,
            last_used_at=link.last_used_at,
        )
        for link, device in db.execute(device_stmt).all()
    ]

    session_stmt = (
        select(SessionModel, Device)
        .outerjoin(Device, SessionModel.device_id == Device.device_id)
        .where(SessionModel.user_id == user.user_id, SessionModel.status == "active")
        .order_by(SessionModel.started_at.desc())
        .limit(10)
    )
    active_sessions = [
        ActiveSessionOut(
            session_id=str(s.session_id),
            device_label=(" ".join(p for p in (d.os, d.browser) if p) or None) if d else None,
            location=", ".join(p for p in (s.geo_city, s.geo_country) if p) or None,
            started_at=s.started_at,
        )
        for s, d in db.execute(session_stmt).all()
    ]

    return SecuritySettingsOut(trusted_devices=trusted_devices, active_sessions=active_sessions)
