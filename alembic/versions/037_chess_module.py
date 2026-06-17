"""Chess module: games, puzzles, attempts, positions, study sets, matches.

Adds the Phase-1 chess tables. All scope-aware tables carry scope_type/scope_id
mirroring sources/wiki_pages so the existing permission engine applies verbatim.
ChessMatch is created here but only exercised in Phase 3 (sparring).

Revision ID: 037_chess_module
Revises: 036_verbatim_sources
Create Date: 2026-06-17
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "037_chess_module"
down_revision = "036_verbatim_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pg_trgm powers fuzzy player/opening search on chess_games.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # --- chess_games ---
    op.create_table(
        "chess_games",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("pgn", sa.Text, nullable=False),
        sa.Column("headers", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("white", sa.String(200)),
        sa.Column("black", sa.String(200)),
        sa.Column("result", sa.String(10)),
        sa.Column("eco", sa.String(4)),
        sa.Column("opening_name", sa.String(300)),
        sa.Column("white_elo", sa.Integer),
        sa.Column("black_elo", sa.Integer),
        sa.Column("event", sa.String(300)),
        sa.Column("played_at", sa.String(20)),
        sa.Column("ply_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("final_fen", sa.String(120)),
        sa.Column("knowledge_type_slugs", postgresql.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("source_game", sa.String(20), nullable=False, server_default="import"),
        sa.Column("match_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("scope_type", sa.String(20), nullable=False, server_default="global"),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "contributed_by_employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_chess_games_scope", "chess_games", ["scope_type", "scope_id"])
    op.create_index("ix_chess_games_eco", "chess_games", ["eco"])
    op.create_index("ix_chess_games_result", "chess_games", ["result"])
    op.execute("CREATE INDEX ix_chess_games_headers ON chess_games USING gin (headers)")
    op.execute(
        "CREATE INDEX ix_chess_games_white_trgm ON chess_games USING gin (white gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_chess_games_black_trgm ON chess_games USING gin (black gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_chess_games_opening_trgm ON chess_games USING gin (opening_name gin_trgm_ops)"
    )

    # --- chess_puzzles ---
    op.create_table(
        "chess_puzzles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fen", sa.String(120), nullable=False),
        sa.Column("solution_moves", postgresql.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("side_to_move", sa.String(1), nullable=False, server_default="w"),
        sa.Column("themes", postgresql.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("rating", sa.Integer),
        sa.Column("popularity", sa.Integer),
        sa.Column(
            "source_game_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chess_games.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(300)),
        sa.Column("description", sa.Text),
        sa.Column("is_published", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("scope_type", sa.String(20), nullable=False, server_default="global"),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_by_employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_chess_puzzles_scope", "chess_puzzles", ["scope_type", "scope_id"])
    op.create_index("ix_chess_puzzles_rating", "chess_puzzles", ["rating"])
    op.create_index("ix_chess_puzzles_published", "chess_puzzles", ["is_published"])
    op.execute("CREATE INDEX ix_chess_puzzles_themes ON chess_puzzles USING gin (themes)")

    # --- chess_puzzle_attempts ---
    op.create_table(
        "chess_puzzle_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "puzzle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chess_puzzles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("solved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("moves_played", postgresql.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("time_ms", sa.Integer),
        sa.Column("hints_used", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rating_before", sa.Integer),
        sa.Column("rating_after", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_chess_puzzle_attempts_employee", "chess_puzzle_attempts", ["employee_id", "created_at"]
    )
    op.create_index("ix_chess_puzzle_attempts_puzzle", "chess_puzzle_attempts", ["puzzle_id"])

    # --- chess_positions ---
    op.create_table(
        "chess_positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fen", sa.String(120), nullable=False),
        sa.Column("label", sa.String(300)),
        sa.Column("description", sa.Text),
        sa.Column("eval_cp", sa.Integer),
        sa.Column("best_move", sa.String(10)),
        sa.Column("eval_depth", sa.Integer),
        sa.Column("themes", postgresql.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("scope_type", sa.String(20), nullable=False, server_default="global"),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_by_employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("scope_type", "scope_id", "fen", name="uq_chess_positions_scope_fen"),
    )
    op.create_index("ix_chess_positions_scope", "chess_positions", ["scope_type", "scope_id"])

    # --- chess_study_sets ---
    op.create_table(
        "chess_study_sets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("kind", sa.String(20), nullable=False, server_default="mixed"),
        sa.Column("wiki_slug", sa.String(300)),
        sa.Column("scope_type", sa.String(20), nullable=False, server_default="global"),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_by_employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_chess_study_sets_scope", "chess_study_sets", ["scope_type", "scope_id"])

    # --- chess_study_items ---
    op.create_table(
        "chess_study_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "study_set_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chess_study_sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("item_type", sa.String(20), nullable=False),
        sa.Column(
            "game_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chess_games.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "puzzle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chess_puzzles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "fen_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chess_positions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("note", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_chess_study_items_set", "chess_study_items", ["study_set_id", "position"])

    # --- chess_matches (defined now, used in Phase 3) ---
    op.create_table(
        "chess_matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "white_employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "black_employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("mode", sa.String(20), nullable=False, server_default="human_vs_engine"),
        sa.Column("engine_level", sa.Integer),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column(
            "current_fen", sa.String(120), nullable=False,
            server_default="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        ),
        sa.Column("moves", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("result", sa.String(10)),
        sa.Column("time_control", sa.String(30)),
        sa.Column(
            "winner_employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "game_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chess_games.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("scope_type", sa.String(20), nullable=False, server_default="global"),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_chess_matches_status", "chess_matches", ["status"])
    op.create_index("ix_chess_matches_white", "chess_matches", ["white_employee_id"])
    op.create_index("ix_chess_matches_black", "chess_matches", ["black_employee_id"])

    # Seed the "chess" knowledge type (idempotent).
    op.execute(
        """
        INSERT INTO knowledge_types (id, slug, name, color, description, sort_order, created_at)
        VALUES (gen_random_uuid(), 'chess', 'Chess', '#c2652a',
                'Chess theory, annotated games, openings and tactics.', 100, now())
        ON CONFLICT (slug) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM knowledge_types WHERE slug = 'chess'")
    op.drop_table("chess_matches")
    op.drop_table("chess_study_items")
    op.drop_table("chess_study_sets")
    op.drop_table("chess_positions")
    op.drop_table("chess_puzzle_attempts")
    op.drop_table("chess_puzzles")
    op.execute("DROP INDEX IF EXISTS ix_chess_games_opening_trgm")
    op.execute("DROP INDEX IF EXISTS ix_chess_games_black_trgm")
    op.execute("DROP INDEX IF EXISTS ix_chess_games_white_trgm")
    op.execute("DROP INDEX IF EXISTS ix_chess_games_headers")
    op.drop_table("chess_games")
