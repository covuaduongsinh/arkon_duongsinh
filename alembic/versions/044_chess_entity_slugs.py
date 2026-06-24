"""Human-readable slugs for chess entities (wikilink targets).

Adds a `slug` column to chess_games, chess_positions, chess_puzzles and
chess_study_sets so each becomes a first-class `[[game:<slug>]]` /
`[[position:<slug>]]` / `[[puzzle:<slug>]]` / `[[study:<slug>]]` wikilink target.
The slug is unique *per scope* (scope_type, scope_id) — NULLs stay distinct in
Postgres, so rows without a slug never collide. Existing rows are backfilled
with readable slugs derived from players/title/label, falling back to a short
id when there's nothing to slugify.

Revision ID: 044_chess_entity_slugs
Revises: 043_wiki_aliases_lesson_links
Create Date: 2026-06-24

Note: the revision id is kept <= 32 chars because alembic_version.version_num
is VARCHAR(32); a longer id fails at the final stamp (StringDataRightTruncation).
"""

import re
import unicodedata

import sqlalchemy as sa

from alembic import op

revision = "044_chess_entity_slugs"
down_revision = "043_wiki_aliases_lesson_links"
branch_labels = None
depends_on = None


# Self-contained slugify (migrations must not depend on mutable app code).
# Handles Vietnamese: strips diacritics and maps đ/Đ → d before normalizing.
def _slugify(text: str, max_len: int = 80) -> str:
    if not text:
        return ""
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text[:max_len].strip("-")


def _game_base(r) -> str:
    parts = [r.get("white"), r.get("black"), r.get("event")]
    label = "-".join(p for p in parts if p and p.strip() and p.strip() != "?")
    year = ""
    if r.get("played_at"):
        m = re.match(r"(\d{4})", r["played_at"])
        if m:
            year = m.group(1)
    return f"{label}-{year}" if year else label


def _backfill(conn, table: str, base_fn, fallback_prefix: str) -> None:
    rows = conn.execute(sa.text(f"SELECT * FROM {table}")).mappings().all()
    used: dict[tuple, set[str]] = {}
    for r in rows:
        key = (r["scope_type"], r["scope_id"])
        seen = used.setdefault(key, set())
        base = _slugify(base_fn(r)) or f"{fallback_prefix}-{str(r['id'])[:8]}"
        slug = base
        n = 2
        while slug in seen:
            slug = f"{base}-{n}"
            n += 1
        seen.add(slug)
        conn.execute(
            sa.text(f"UPDATE {table} SET slug = :slug WHERE id = :id"),
            {"slug": slug, "id": r["id"]},
        )


_TABLES = [
    ("chess_games", _game_base, "game", "uq_chess_games_scope_slug"),
    ("chess_positions", (lambda r: r.get("label")), "position", "uq_chess_positions_scope_slug"),
    ("chess_puzzles", (lambda r: r.get("title")), "puzzle", "uq_chess_puzzles_scope_slug"),
    ("chess_study_sets", (lambda r: r.get("title")), "study", "uq_chess_study_sets_scope_slug"),
]


def upgrade() -> None:
    conn = op.get_bind()
    # 1. Add nullable slug columns.
    for table, _base, _prefix, _uq in _TABLES:
        op.add_column(table, sa.Column("slug", sa.String(120), nullable=True))
    # 2. Backfill readable slugs (unique within each scope).
    for table, base_fn, prefix, _uq in _TABLES:
        _backfill(conn, table, base_fn, prefix)
    # 3. Enforce per-scope uniqueness (NULLs remain distinct).
    for table, _base, _prefix, uq in _TABLES:
        op.create_unique_constraint(uq, table, ["scope_type", "scope_id", "slug"])


def downgrade() -> None:
    for table, _base, _prefix, uq in _TABLES:
        op.drop_constraint(uq, table, type_="unique")
        op.drop_column(table, "slug")
