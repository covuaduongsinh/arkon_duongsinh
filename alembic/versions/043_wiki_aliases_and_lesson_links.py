"""Wiki page aliases + chess lesson→wiki link edges.

Two additions that improve wikilink quality and connectivity:

  * wiki_pages.aliases (text[]) — VN/EN synonyms that resolve to a page's slug
    when used as a `[[wikilink]]` target (e.g. "fork"/"nĩa" → chien-thuat-nia-fork).
    Targets are rewritten to the canonical slug at upsert time; lint and the
    autocomplete also treat aliases as valid link targets. GIN index for fast
    containment lookups.
  * chess_lesson_links (lesson_id, to_slug) — derived edges parsed from a chess
    lesson's content_md `[[slug]]` patterns, mirroring wiki_links. Lets a concept
    page surface "which lessons reference me" (chess ↔ wiki, second direction).

Revision ID: 043_wiki_aliases_and_lesson_links
Revises: 042_chess_knowledge_links
Create Date: 2026-06-23
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "043_wiki_aliases_and_lesson_links"
down_revision = "042_chess_knowledge_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Wiki page aliases ---
    op.add_column(
        "wiki_pages",
        sa.Column(
            "aliases",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.create_index(
        "ix_wiki_pages_aliases", "wiki_pages", ["aliases"], postgresql_using="gin"
    )

    # --- Chess lesson → wiki link edges ---
    op.create_table(
        "chess_lesson_links",
        sa.Column(
            "lesson_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chess_lessons.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("to_slug", sa.String(300), nullable=False),
        sa.PrimaryKeyConstraint("lesson_id", "to_slug"),
    )
    op.create_index(
        "ix_chess_lesson_links_lesson_id", "chess_lesson_links", ["lesson_id"]
    )
    op.create_index(
        "ix_chess_lesson_links_to_slug", "chess_lesson_links", ["to_slug"]
    )


def downgrade() -> None:
    op.drop_index("ix_chess_lesson_links_to_slug", table_name="chess_lesson_links")
    op.drop_index("ix_chess_lesson_links_lesson_id", table_name="chess_lesson_links")
    op.drop_table("chess_lesson_links")
    op.drop_index("ix_wiki_pages_aliases", table_name="wiki_pages")
    op.drop_column("wiki_pages", "aliases")
