"""Chess ↔ Knowledge links: sub-topic taxonomy + verbatim index / companion-page columns.

Seeds the chess knowledge-type "family" (chess-opening / chess-tactics /
chess-endgame / chess-strategy / chess-game) alongside the existing flat "chess"
type, and adds the columns that wire chess content into the knowledge base:

  * chess_lessons.indexed_source_id  — the verbatim Source that mirrors this
    lesson into the semantic search pool (so search_wiki finds lessons).
  * chess_lessons.wiki_slug          — optional companion wiki page (mirrors
    chess_study_sets.wiki_slug) set when a publish-to-wiki draft is approved.
  * chess_study_sets.indexed_source_id — same verbatim-index link for study sets.

No schema change to knowledge_types — the "chess family" is simply every slug
starting with 'chess' (see chess_service.chess_family_kt_slugs).

Revision ID: 042_chess_knowledge_links
Revises: 041_chess_lms
Create Date: 2026-06-18
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "042_chess_knowledge_links"
down_revision = "041_chess_lms"
branch_labels = None
depends_on = None


# (slug, name, description, sort_order)
_CHESS_SUBTOPICS = [
    ("chess-opening", "Chess · Openings", "Opening theory, repertoires and move-order ideas.", 101),
    ("chess-tactics", "Chess · Tactics", "Tactical motifs, combinations and puzzle themes.", 102),
    ("chess-endgame", "Chess · Endgames", "Endgame technique, theoretical positions and conversion.", 103),
    ("chess-strategy", "Chess · Strategy", "Positional play, plans, pawn structures and middlegame strategy.", 104),
    ("chess-game", "Chess · Annotated games", "Annotated games and model-game collections.", 105),
]


def upgrade() -> None:
    # --- 1A. Seed chess sub-topic knowledge types (idempotent, shared color). ---
    for slug, name, description, sort_order in _CHESS_SUBTOPICS:
        op.execute(
            sa.text(
                """
                INSERT INTO knowledge_types (id, slug, name, color, description, sort_order, created_at)
                VALUES (gen_random_uuid(), :slug, :name, '#c2652a', :description, :sort_order, now())
                ON CONFLICT (slug) DO NOTHING
                """
            ).bindparams(slug=slug, name=name, description=description, sort_order=sort_order)
        )

    # --- 1B/1D. Verbatim-index + companion-page link columns. ---
    op.add_column(
        "chess_lessons",
        sa.Column(
            "indexed_source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("chess_lessons", sa.Column("wiki_slug", sa.String(300), nullable=True))
    op.add_column(
        "chess_study_sets",
        sa.Column(
            "indexed_source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("chess_study_sets", "indexed_source_id")
    op.drop_column("chess_lessons", "wiki_slug")
    op.drop_column("chess_lessons", "indexed_source_id")
    op.execute(
        "DELETE FROM knowledge_types WHERE slug IN "
        "('chess-opening','chess-tactics','chess-endgame','chess-strategy','chess-game')"
    )
