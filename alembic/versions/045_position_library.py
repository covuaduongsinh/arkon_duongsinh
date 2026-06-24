"""Enrich the chess position library + Lichess-shaped puzzle attributes.

Turns `chess_positions` from a bare FEN store into a richly retrievable library:
adds difficulty / popularity / nb_plays / piece_count / side_to_move / eco /
opening_name / source / source_puzzle_id (a link back to the puzzle a position
was synced from). `chess_puzzles` gains the remaining Lichess attributes
(opening_name, nb_plays, source, lichess_id) so the Lichess puzzle CSV imports
cleanly, then a sync step projects puzzles into the position library.

All new columns are nullable and additive. piece_count + side_to_move are
backfilled from each existing FEN; existing positions get source='manual'.

Revision ID: 045_position_library
Revises: 044_chess_entity_slugs
Create Date: 2026-06-24

Note: the revision id is kept <= 32 chars because alembic_version.version_num
is VARCHAR(32); a longer id fails at the final stamp (StringDataRightTruncation).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "045_position_library"
down_revision = "044_chess_entity_slugs"
branch_labels = None
depends_on = None


# Self-contained FEN facts (migrations must not depend on mutable app code).
def _fen_facts(fen: str) -> tuple[int, str]:
    """Return (piece_count, side_to_move) from a FEN string."""
    parts = (fen or "").split()
    placement = parts[0] if parts else ""
    piece_count = sum(1 for c in placement if c.isalpha())
    side = parts[1] if len(parts) > 1 and parts[1] in ("w", "b") else "w"
    return piece_count, side


def upgrade() -> None:
    conn = op.get_bind()

    # --- chess_puzzles: remaining Lichess attributes ---
    op.add_column("chess_puzzles", sa.Column("nb_plays", sa.Integer(), nullable=True))
    op.add_column("chess_puzzles", sa.Column("opening_name", sa.String(160), nullable=True))
    op.add_column("chess_puzzles", sa.Column("source", sa.String(20), nullable=True))
    op.add_column("chess_puzzles", sa.Column("lichess_id", sa.String(40), nullable=True))
    op.create_index(
        "uq_chess_puzzles_lichess_id", "chess_puzzles", ["lichess_id"], unique=True,
    )

    # --- chess_positions: library retrieval attributes ---
    op.add_column("chess_positions", sa.Column("difficulty", sa.Integer(), nullable=True))
    op.add_column("chess_positions", sa.Column("popularity", sa.Integer(), nullable=True))
    op.add_column("chess_positions", sa.Column("nb_plays", sa.Integer(), nullable=True))
    op.add_column("chess_positions", sa.Column("piece_count", sa.Integer(), nullable=True))
    op.add_column("chess_positions", sa.Column("side_to_move", sa.String(1), nullable=True))
    op.add_column("chess_positions", sa.Column("eco", sa.String(8), nullable=True))
    op.add_column("chess_positions", sa.Column("opening_name", sa.String(160), nullable=True))
    op.add_column("chess_positions", sa.Column("source", sa.String(20), nullable=True))
    op.add_column(
        "chess_positions",
        sa.Column("source_puzzle_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_chess_positions_source_puzzle", "chess_positions", "chess_puzzles",
        ["source_puzzle_id"], ["id"], ondelete="SET NULL",
    )

    # Backfill piece_count + side_to_move from existing FENs; mark source.
    rows = conn.execute(sa.text("SELECT id, fen FROM chess_positions")).mappings().all()
    for r in rows:
        pc, side = _fen_facts(r["fen"])
        conn.execute(
            sa.text(
                "UPDATE chess_positions "
                "SET piece_count = :pc, side_to_move = :side, source = 'manual' "
                "WHERE id = :id"
            ),
            {"pc": pc, "side": side, "id": r["id"]},
        )

    op.create_index("ix_chess_positions_difficulty", "chess_positions", ["difficulty"])
    op.create_index("ix_chess_positions_piece_count", "chess_positions", ["piece_count"])
    op.create_index("ix_chess_positions_popularity", "chess_positions", ["popularity"])
    op.create_index("ix_chess_positions_eco", "chess_positions", ["eco"])
    op.create_index("ix_chess_positions_source", "chess_positions", ["source"])
    op.create_index(
        "ix_chess_positions_themes", "chess_positions", ["themes"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_chess_positions_themes", table_name="chess_positions")
    op.drop_index("ix_chess_positions_source", table_name="chess_positions")
    op.drop_index("ix_chess_positions_eco", table_name="chess_positions")
    op.drop_index("ix_chess_positions_popularity", table_name="chess_positions")
    op.drop_index("ix_chess_positions_piece_count", table_name="chess_positions")
    op.drop_index("ix_chess_positions_difficulty", table_name="chess_positions")
    op.drop_constraint(
        "fk_chess_positions_source_puzzle", "chess_positions", type_="foreignkey",
    )
    for col in (
        "source_puzzle_id", "source", "opening_name", "eco", "side_to_move",
        "piece_count", "nb_plays", "popularity", "difficulty",
    ):
        op.drop_column("chess_positions", col)

    op.drop_index("uq_chess_puzzles_lichess_id", table_name="chess_puzzles")
    for col in ("lichess_id", "source", "opening_name", "nb_plays"):
        op.drop_column("chess_puzzles", col)
