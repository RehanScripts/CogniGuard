"""SQLAlchemy models (OLTP system of record). Importing this package registers all
16 tables on ``Base.metadata`` so Alembic autogenerate and create_all see them."""

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
]
