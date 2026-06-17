"""Chess LMS: classes, members, lessons, assignments (Roadmap D).

Revision ID: 041_chess_lms
Revises: 040_game_analysis
Create Date: 2026-06-18
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "041_chess_lms"
down_revision = "040_game_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chess_classes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("coach_employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("scope_type", sa.String(20), nullable=False, server_default="global"),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_chess_classes_coach", "chess_classes", ["coach_employee_id"])

    op.create_table(
        "chess_class_members",
        sa.Column("class_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chess_classes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="student"),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_chess_class_members_employee", "chess_class_members", ["employee_id"])

    op.create_table(
        "chess_lessons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("class_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chess_classes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("content_md", sa.Text, nullable=False, server_default=""),
        sa.Column("study_set_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chess_study_sets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_by_employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_chess_lessons_class", "chess_lessons", ["class_id", "position"])

    op.create_table(
        "chess_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("class_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chess_classes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("kind", sa.String(20), nullable=False, server_default="puzzles"),
        sa.Column("puzzle_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False, server_default="{}"),
        sa.Column("study_set_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chess_study_sets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chess_lessons.id", ondelete="SET NULL"), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_chess_assignments_class", "chess_assignments", ["class_id"])


def downgrade() -> None:
    op.drop_table("chess_assignments")
    op.drop_table("chess_lessons")
    op.drop_table("chess_class_members")
    op.drop_table("chess_classes")
