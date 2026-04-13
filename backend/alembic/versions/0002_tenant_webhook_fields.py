"""add webhook fields to tenants

Revision ID: 0002_webhook
Revises: 0001_initial
Create Date: 2026-04-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_webhook"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("webhook_url", sa.String(500), nullable=True))
    op.add_column("tenants", sa.Column("webhook_secret", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "webhook_secret")
    op.drop_column("tenants", "webhook_url")
