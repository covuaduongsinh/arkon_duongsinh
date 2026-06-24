"""Game Library: add curation/publish/filter columns to chess_games.

Upgrades the Games feature into a browsable, filterable, curated library (mirroring
the puzzle library): draft/publish workflow, coach curation (title/description/themes),
denormalized filter fields (site, played_year) and metric fields (popularity, plus
blunder/brilliant counts derived from engine analysis — Phase B).

Backfill: existing games are marked is_published=true (they were already visible, so
turning on the draft gate must not hide them); site + played_year + blunder_count are
denormalized from existing data. New imports default to draft (is_published=false).

All additive — no destructive changes.

Revision ID: 049_game_library
Revises: 048_puzzle_setup_move
Create Date: 2026-06-24

Note: revision id kept <= 32 chars (alembic_version.version_num is VARCHAR(32)).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "049_game_library"
down_revision = "048_puzzle_setup_move"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chess_games", sa.Column(
        "is_published", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("chess_games", sa.Column("title", sa.String(length=300), nullable=True))
    op.add_column("chess_games", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("chess_games", sa.Column(
        "themes", postgresql.ARRAY(sa.String()), nullable=False, server_default=sa.text("'{}'::varchar[]")))
    op.add_column("chess_games", sa.Column("site", sa.String(length=200), nullable=True))
    op.add_column("chess_games", sa.Column("played_year", sa.Integer(), nullable=True))
    op.add_column("chess_games", sa.Column(
        "popularity", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("chess_games", sa.Column("blunder_count", sa.Integer(), nullable=True))
    op.add_column("chess_games", sa.Column("brilliant_count", sa.Integer(), nullable=True))

    op.create_index("ix_chess_games_published", "chess_games", ["is_published"])
    op.create_index("ix_chess_games_played_year", "chess_games", ["played_year"])
    op.create_index("ix_chess_games_popularity", "chess_games", ["popularity"])
    op.create_index("ix_chess_games_themes", "chess_games", ["themes"], postgresql_using="gin")

    conn = op.get_bind()
    # Existing games stay visible after the draft gate turns on.
    conn.execute(sa.text("UPDATE chess_games SET is_published = true"))
    # Denormalize Site from the raw PGN headers.
    conn.execute(sa.text(
        "UPDATE chess_games SET site = LEFT(headers->>'Site', 200) "
        "WHERE headers ? 'Site' AND COALESCE(headers->>'Site','') <> ''"
    ))
    # Year from the leading 4 digits of played_at (PGN dates are often partial).
    conn.execute(sa.text(
        "UPDATE chess_games SET played_year = LEFT(played_at, 4)::int "
        "WHERE played_at ~ '^[0-9]{4}'"
    ))
    # Blunder count from any existing completed analysis.
    conn.execute(sa.text(
        "UPDATE chess_games SET blunder_count = (analysis_json->'summary'->>'blunder')::int "
        "WHERE analysis_status = 'done' AND analysis_json ? 'summary' "
        "AND (analysis_json->'summary') ? 'blunder'"
    ))


def downgrade() -> None:
    op.drop_index("ix_chess_games_themes", table_name="chess_games")
    op.drop_index("ix_chess_games_popularity", table_name="chess_games")
    op.drop_index("ix_chess_games_played_year", table_name="chess_games")
    op.drop_index("ix_chess_games_published", table_name="chess_games")
    for col in ("brilliant_count", "blunder_count", "popularity", "played_year",
                "site", "themes", "description", "title", "is_published"):
        op.drop_column("chess_games", col)
