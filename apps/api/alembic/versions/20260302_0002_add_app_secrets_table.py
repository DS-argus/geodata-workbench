"""add app_secrets table

Revision ID: 20260302_0002
Revises: 20260301_0001
Create Date: 2026-03-02 09:40:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260302_0002"
down_revision = "20260301_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_secrets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("secret_key", sa.String(length=128), nullable=False, unique=True),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("app_secrets")
