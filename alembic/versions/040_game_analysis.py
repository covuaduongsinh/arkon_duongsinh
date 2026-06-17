"""Async whole-game analysis fields on chess_games.

Revision ID: 040_game_analysis
Revises: 039_puzzle_rating
Create Date: 2026-06-18
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "040_game_analysis"
down_revision = "039_puzzle_rating"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chess_games", sa.Column("analysis_status", sa.String(20), nullable=False, server_default="none"))
    op.add_column("chess_games", sa.Column("analysis_json", postgresql.JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("chess_games", "analysis_json")
    op.drop_column("chess_games", "analysis_status")
