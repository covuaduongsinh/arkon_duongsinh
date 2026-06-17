"""External self-signup users: is_external + email verification fields.

Adds columns to employees so self-registered students/customers (Roadmap A)
can be distinguished from internal staff and gated by email verification /
admin approval.

Revision ID: 038_external_users
Revises: 037_chess_module
Create Date: 2026-06-18
"""

import sqlalchemy as sa

from alembic import op

revision = "038_external_users"
down_revision = "037_chess_module"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("is_external", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("employees", sa.Column("email_verified", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("employees", sa.Column("verification_token_hash", sa.String(64), nullable=True))
    op.add_column("employees", sa.Column("verification_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_employees_verification_token_hash",
        "employees",
        ["verification_token_hash"],
        unique=False,
        postgresql_where=sa.text("verification_token_hash IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_employees_verification_token_hash", table_name="employees")
    op.drop_column("employees", "verification_sent_at")
    op.drop_column("employees", "verification_token_hash")
    op.drop_column("employees", "email_verified")
    op.drop_column("employees", "is_external")
