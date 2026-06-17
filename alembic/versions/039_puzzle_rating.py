"""Per-student puzzle rating (Elo) on employees.

Revision ID: 039_puzzle_rating
Revises: 038_external_users
Create Date: 2026-06-18
"""

import sqlalchemy as sa

from alembic import op

revision = "039_puzzle_rating"
down_revision = "038_external_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("puzzle_rating", sa.Integer(), nullable=False, server_default="1200"),
    )


def downgrade() -> None:
    op.drop_column("employees", "puzzle_rating")
