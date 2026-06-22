"""Admin/analyst login (Phase 30) -- mirrors `auth_flow.login`'s shape but issues the
separate admin-track JWT (`security.issue_admin_jwt`) rather than the customer-session
JWT, so admin tokens can never be presented to customer-only endpoints or vice versa.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..models.analyst import Analyst
from ..schemas.admin import AdminLoginRequest, AdminLoginResponse
from ..utils import security


def login(db: DbSession, req: AdminLoginRequest) -> AdminLoginResponse | None:
    """Returns None on bad credentials/inactive analyst -- the router maps that to 401."""
    analyst = db.scalar(select(Analyst).where(Analyst.email == req.email))
    if analyst is None or analyst.status != "active":
        return None
    if not security.verify_password(req.password, analyst.password_hash):
        return None

    token, _ = security.issue_admin_jwt(str(analyst.analyst_id), analyst.role)
    return AdminLoginResponse(
        token=token,
        analyst_id=str(analyst.analyst_id),
        role=analyst.role,
        full_name=analyst.full_name,
    )
