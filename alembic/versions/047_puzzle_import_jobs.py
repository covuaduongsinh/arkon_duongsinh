"""Add chess_puzzle_import_jobs — track web-driven Lichess puzzle DB imports.

A coach kicks off a Lichess import from the web (URL fetch or file upload); the
work runs as a background arq job. This table holds the job's status + running
counts so the UI can poll progress. Purely additive — creates one new table.

Revision ID: 047_puzzle_import_jobs
Revises: 046_puzzle_piece_count
Create Date: 2026-06-24

Note: the revision id is kept <= 32 chars because alembic_version.version_num
is VARCHAR(32); a longer id fails at the final stamp (StringDataRightTruncation).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "047_puzzle_import_jobs"
down_revision = "046_puzzle_piece_count"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chess_puzzle_import_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_kind", sa.String(length=10), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column(
            "params_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("rows_read", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("positions_synced", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["employees.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_chess_puzzle_import_jobs_status",
        "chess_puzzle_import_jobs",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chess_puzzle_import_jobs_status", table_name="chess_puzzle_import_jobs")
    op.drop_table("chess_puzzle_import_jobs")
