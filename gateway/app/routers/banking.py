"""Banking router (Phase 28, authorized exception) -- thin, read-only GET endpoints
over existing Account/Transaction/Beneficiary/User models. All behind
`deps.get_current_user`; no writes, no new models, no security telemetry."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session as DbSession

from .. import deps
from ..models.session import Session as SessionModel
from ..models.user import User
from ..schemas.banking import (
    AccountOut,
    BeneficiaryOut,
    ProfileOut,
    SecuritySettingsOut,
    TransactionOut,
)
from ..services import banking

router = APIRouter()


@router.get("/profile", response_model=ProfileOut)
def profile(current: tuple[User, SessionModel] = Depends(deps.get_current_user)) -> ProfileOut:
    user, _ = current
    return banking.get_profile(user)


@router.get("/accounts", response_model=list[AccountOut])
def accounts(
    db: DbSession = Depends(deps.get_db),
    current: tuple[User, SessionModel] = Depends(deps.get_current_user),
) -> list[AccountOut]:
    user, _ = current
    return banking.list_accounts(db, user)


@router.get("/transactions", response_model=list[TransactionOut])
def transactions(
    limit: int = Query(default=50, le=200),
    db: DbSession = Depends(deps.get_db),
    current: tuple[User, SessionModel] = Depends(deps.get_current_user),
) -> list[TransactionOut]:
    user, _ = current
    return banking.list_transactions(db, user, limit=limit)


@router.get("/beneficiaries", response_model=list[BeneficiaryOut])
def beneficiaries(
    db: DbSession = Depends(deps.get_db),
    current: tuple[User, SessionModel] = Depends(deps.get_current_user),
) -> list[BeneficiaryOut]:
    user, _ = current
    return banking.list_beneficiaries(db, user)


@router.get("/security-settings", response_model=SecuritySettingsOut)
def security_settings(
    db: DbSession = Depends(deps.get_db),
    current: tuple[User, SessionModel] = Depends(deps.get_current_user),
) -> SecuritySettingsOut:
    user, _ = current
    return banking.get_security_settings(db, user)
