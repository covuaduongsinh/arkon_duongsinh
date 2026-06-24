"""Add setup_move/setup_fen to chess_puzzles + normalize existing Lichess puzzles.

Lichess puzzle `Moves` start with the opponent's lead-in move (auto-played), then
the solver's solution. The dump's FEN is the position BEFORE that lead-in move, so
previously imported rows had: fen = pre-lead-in, side_to_move = opponent, and the
lead-in move wrongly sitting at solution_moves[0].

This migration:
  - adds nullable `setup_move` (UCI) and `setup_fen` (pre-lead-in FEN),
  - backfills source='lichess' rows by applying the lead-in move so that
    fen = solve position, side_to_move = solver, solution_moves = the real solution,
    setup_fen = old fen, setup_move = the lead-in move.

Idempotent: only rows with setup_move IS NULL and >=2 solution moves are touched.

Revision ID: 048_puzzle_setup_move
Revises: 047_puzzle_import_jobs
Create Date: 2026-06-24

Note: revision id kept <= 32 chars (alembic_version.version_num is VARCHAR(32)).
"""

import chess  # python-chess is a project dependency; safe to use in-migration.
import sqlalchemy as sa
from loguru import logger
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "048_puzzle_setup_move"
down_revision = "047_puzzle_import_jobs"
branch_labels = None
depends_on = None


def _piece_count(fen: str) -> int:
    placement = (fen or "").split(" ")[0]
    return sum(1 for c in placement if c.isalpha())


def _side(fen: str) -> str:
    parts = (fen or "").split()
    return parts[1] if len(parts) > 1 and parts[1] in ("w", "b") else "w"


def _apply(fen: str, uci: str):
    """Return the FEN after playing `uci` on `fen`, or None if illegal."""
    try:
        board = chess.Board(fen)
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            return None
        board.push(move)
        return board.fen()
    except Exception:
        return None


def upgrade() -> None:
    op.add_column("chess_puzzles", sa.Column("setup_move", sa.String(length=10), nullable=True))
    op.add_column("chess_puzzles", sa.Column("setup_fen", sa.String(length=120), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, fen, solution_moves FROM chess_puzzles "
        "WHERE source = 'lichess' AND setup_move IS NULL "
        "AND array_length(solution_moves, 1) >= 2"
    )).mappings().all()

    # Type the array bindparam explicitly so it adapts correctly under asyncpg.
    update_stmt = sa.text(
        "UPDATE chess_puzzles SET "
        "setup_fen = :setup_fen, setup_move = :setup_move, fen = :post_fen, "
        "solution_moves = :solution, side_to_move = :side, piece_count = :pc "
        "WHERE id = :id"
    ).bindparams(sa.bindparam("solution", type_=postgresql.ARRAY(sa.String())))

    normalized = skipped = 0
    for r in rows:
        moves = list(r["solution_moves"] or [])
        setup = moves[0]
        post_fen = _apply(r["fen"], setup)
        if post_fen is None:
            skipped += 1
            continue
        conn.execute(
            update_stmt,
            {
                "setup_fen": r["fen"],
                "setup_move": setup,
                "post_fen": post_fen,
                "solution": moves[1:],
                "side": _side(post_fen),
                "pc": _piece_count(post_fen),
                "id": r["id"],
            },
        )
        normalized += 1

    logger.info(f"048_puzzle_setup_move: normalized {normalized} Lichess puzzles, skipped {skipped}")


def downgrade() -> None:
    # The lead-in normalization is not reversed (lossy); only drop the columns.
    op.drop_column("chess_puzzles", "setup_fen")
    op.drop_column("chess_puzzles", "setup_move")
