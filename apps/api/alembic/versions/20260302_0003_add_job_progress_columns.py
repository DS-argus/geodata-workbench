"""add progress columns to jobs

Revision ID: 20260302_0003
Revises: 20260302_0002
Create Date: 2026-03-02 22:40:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260302_0003"
down_revision = "20260302_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("jobs", sa.Column("progress_message", sa.Text(), nullable=True))
    op.alter_column("jobs", "progress_percent", server_default=None)


def downgrade() -> None:
    op.drop_column("jobs", "progress_message")
    op.drop_column("jobs", "progress_percent")
