"""add gemini_api_key_encrypted to tenants

Revision ID: 0003_gemini_key
Revises: 0002_webhook
Create Date: 2026-04-26

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_gemini_key"
down_revision: Union[str, None] = "0002_webhook"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("gemini_api_key_encrypted", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "gemini_api_key_encrypted")
