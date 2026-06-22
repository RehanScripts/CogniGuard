"""SQLAlchemy models (OLTP system of record). Importing this package registers all
tables on ``Base.metadata`` so Alembic autogenerate and create_all see them. The
canonical 16 tables are PRD §17.1's schema; `Analyst` (Phase 30) is a documented
exception beyond it, same pattern as Phase 28's banking tables."""

from .analyst import Analyst
from .behavior import BehaviorSample
from .beneficiary import Beneficiary, UserBeneficiary
from .device import Device, UserDevice
from .governance import AuditLog, Case, ModelRegistry
from .scoring import AuthChallenge, Decision, RiskScore
from .session import LoginEvent, Session
from .transaction import Transaction
from .user import Account, User

__all__ = [
    "User",
    "Account",
    "Device",
    "UserDevice",
    "Session",
    "LoginEvent",
    "BehaviorSample",
    "Beneficiary",
    "UserBeneficiary",
    "Transaction",
    "RiskScore",
    "Decision",
    "AuthChallenge",
    "Case",
    "AuditLog",
    "ModelRegistry",
    "Analyst",
]
