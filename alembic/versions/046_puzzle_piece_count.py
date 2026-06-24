"""Add piece_count to chess_puzzles for the puzzle library's endgame filter.

Mirrors chess_positions.piece_count: a material count derived from the FEN so
the puzzle library can filter by number of pieces (e.g. endgame ≤7). Additive
nullable column, backfilled from each existing FEN.

Revision ID: 046_puzzle_piece_count
Revises: 045_position_library
Create Date: 2026-06-24

Note: the revision id is kept <= 32 chars because alembic_version.version_num
is VARCHAR(32); a longer id fails at the final stamp (StringDataRightTruncation).
"""

import sqlalchemy as sa

from alembic import op

revision = "046_puzzle_piece_count"
down_revision = "045_position_library"
branch_labels = None
depends_on = None


# Self-contained (migrations must not depend on mutable app code).
def _piece_count(fen: str) -> int:
    placement = (fen or "").split(" ")[0]
    return sum(1 for c in placement if c.isalpha())


def upgrade() -> None:
    conn = op.get_bind()
    op.add_column("chess_puzzles", sa.Column("piece_count", sa.Integer(), nullable=True))

    rows = conn.execute(sa.text("SELECT id, fen FROM chess_puzzles")).mappings().all()
    for r in rows:
        conn.execute(
            sa.text("UPDATE chess_puzzles SET piece_count = :pc WHERE id = :id"),
            {"pc": _piece_count(r["fen"]), "id": r["id"]},
        )

    op.create_index("ix_chess_puzzles_piece_count", "chess_puzzles", ["piece_count"])


def downgrade() -> None:
    op.drop_index("ix_chess_puzzles_piece_count", table_name="chess_puzzles")
    op.drop_column("chess_puzzles", "piece_count")
