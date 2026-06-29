"""phase_c3: add public_key to user_devices for KeyStore biometric binding

Revision ID: c3a1f9d28e7b
Revises: 7ecc6f2ac478
Create Date: 2026-06-27 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3a1f9d28e7b"
down_revision: Union[str, None] = "7ecc6f2ac478"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_devices", sa.Column("public_key", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_devices", "public_key")
