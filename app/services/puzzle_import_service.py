"""Lichess puzzle-DB import — shared core used by the CLI, the API and the worker.

The Lichess puzzle dump (`lichess_db_puzzle.csv` / `.csv.zst`) has columns:

    PuzzleId,FEN,Moves,Rating,RatingDeviation,Popularity,NbPlays,Themes,GameUrl,OpeningTags

Each row lands as one ChessPuzzle (source='lichess', slug='lichess-<id>', deduped on
`lichess_id` via ON CONFLICT DO NOTHING). The full dump is ~4–5M rows — never import it
all into an on-prem Postgres; always filter with a rating/theme/opening filter or a limit.

Both entry points converge on a file on disk:
  - upload → the buffered temp file
  - url    → `download_to_temp()` streams the dump to a temp file first
then `import_from_path()` streams + filters + batch-inserts it. This keeps the CSV reader
fully synchronous (no async/sync bridge) regardless of source.
"""

from __future__ import annotations

import csv
import inspect
import io
import os
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Union

from loguru import logger
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ChessPuzzle
from app.services import chess_service

# Official Lichess puzzle database (Zstandard-compressed CSV).
OFFICIAL_LICHESS_PUZZLE_URL = "https://database.lichess.org/lichess_db_puzzle.csv.zst"

# Hard cap on how many puzzles a single web import may insert — protects on-prem
# Postgres from someone accidentally importing the whole ~5M-row dump.
MAX_IMPORT_LIMIT = 50_000

ProgressCb = Callable[[int, int], Union[None, Awaitable[None]]]


@dataclass
class PuzzleImportFilters:
    """Row filters applied while streaming the dump (mirrors the CLI flags)."""
    min_rating: Optional[int] = None
    max_rating: Optional[int] = None
    theme: Optional[str] = None
    opening: Optional[str] = None
    limit: Optional[int] = None


def validate_filters(filters: PuzzleImportFilters) -> None:
    """Refuse an unbounded import; clamp/validate the limit. Raises ValueError."""
    has_filter = any(
        v is not None for v in (filters.min_rating, filters.max_rating, filters.theme, filters.opening)
    )
    if not filters.limit and not has_filter:
        raise ValueError(
            "Cần ít nhất một bộ lọc (rating/theme/opening) hoặc giới hạn (limit) — "
            "không thể nhập toàn bộ kho Lichess (~5 triệu bài)."
        )
    if filters.limit is not None:
        if filters.limit <= 0:
            raise ValueError("limit phải là số dương.")
        if filters.limit > MAX_IMPORT_LIMIT:
            raise ValueError(f"limit tối đa cho một lần nhập là {MAX_IMPORT_LIMIT:,}.")


# ---------------------------------------------------------------------------
# Row mapping (Lichess CSV → ChessPuzzle values)
# ---------------------------------------------------------------------------

def _to_int(value: Optional[str]) -> Optional[int]:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _opening_name(opening_tags: Optional[str]) -> Optional[str]:
    """Lichess OpeningTags → a readable opening name. Tags are space-separated,
    each underscore-joined; take the most specific (last) and unslug it."""
    tags = (opening_tags or "").split()
    if not tags:
        return None
    return tags[-1].replace("_", " ").replace("-", " ")


def row_to_values(row: dict) -> Optional[dict]:
    fen = (row.get("FEN") or "").strip()
    if not fen:
        return None
    pid = (row.get("PuzzleId") or "").strip()
    piece_count, side = chess_service._fen_facts(fen)
    moves = (row.get("Moves") or "").split()
    themes = (row.get("Themes") or "").split()
    game_url = (row.get("GameUrl") or "").strip()
    return {
        "fen": fen,
        "slug": f"lichess-{pid.lower()}" if pid else None,
        "solution_moves": moves,
        "side_to_move": side,
        "piece_count": piece_count,
        "themes": themes,
        "rating": _to_int(row.get("Rating")),
        "popularity": _to_int(row.get("Popularity")),
        "nb_plays": _to_int(row.get("NbPlays")),
        "opening_name": _opening_name(row.get("OpeningTags")),
        "source": "lichess",
        "lichess_id": pid or None,
        "description": game_url or None,
        "is_published": False,
        "scope_type": "global",
        "scope_id": None,
    }


def passes_filters(row: dict, filters: PuzzleImportFilters) -> bool:
    rating = _to_int(row.get("Rating"))
    if filters.min_rating is not None and (rating is None or rating < filters.min_rating):
        return False
    if filters.max_rating is not None and (rating is None or rating > filters.max_rating):
        return False
    if filters.theme and filters.theme.lower() not in (row.get("Themes") or "").lower():
        return False
    if filters.opening and filters.opening.lower() not in (row.get("OpeningTags") or "").lower():
        return False
    return True


async def insert_batch(session: AsyncSession, batch: list[dict]) -> int:
    if not batch:
        return 0
    stmt = pg_insert(ChessPuzzle).values(batch)
    # Dedupe re-imports on the unique lichess_id index.
    stmt = stmt.on_conflict_do_nothing(index_elements=["lichess_id"])
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount or 0


# ---------------------------------------------------------------------------
# Streaming import
# ---------------------------------------------------------------------------

def open_text_stream_from_path(path: str) -> io.TextIOBase:
    """Yield a text stream for a .csv or .csv.zst file."""
    if path.endswith(".zst"):
        try:
            import zstandard
        except ImportError as e:  # pragma: no cover - dependency is declared
            raise RuntimeError(
                "Reading .zst needs the 'zstandard' package (declared in pyproject)."
            ) from e
        fh = open(path, "rb")
        reader = zstandard.ZstdDecompressor().stream_reader(fh)
        return io.TextIOWrapper(reader, encoding="utf-8", newline="")
    return open(path, "r", encoding="utf-8", newline="")


async def _emit(on_progress: Optional[ProgressCb], rows_read: int, inserted: int) -> None:
    if on_progress is None:
        return
    res = on_progress(rows_read, inserted)
    if inspect.isawaitable(res):
        await res


async def import_from_text_stream(
    session: AsyncSession,
    text_stream: io.TextIOBase,
    *,
    filters: PuzzleImportFilters,
    publish: bool = False,
    batch_size: int = 1000,
    on_progress: Optional[ProgressCb] = None,
) -> dict:
    """Stream rows, filter, and batch-insert. Returns {rows_read, inserted, skipped}.

    `rows_read` counts rows that passed the filters and were attempted (the limit
    applies to these); `skipped` is the duplicate count (already-present lichess_id).
    """
    reader = csv.DictReader(text_stream)
    rows_read = inserted = 0
    batch: list[dict] = []
    for row in reader:
        if filters.limit and rows_read >= filters.limit:
            break
        if not passes_filters(row, filters):
            continue
        values = row_to_values(row)
        if values is None:
            continue
        if publish:
            values["is_published"] = True
        batch.append(values)
        rows_read += 1
        if len(batch) >= batch_size:
            inserted += await insert_batch(session, batch)
            batch = []
            await _emit(on_progress, rows_read, inserted)
    inserted += await insert_batch(session, batch)
    await _emit(on_progress, rows_read, inserted)
    return {"rows_read": rows_read, "inserted": inserted, "skipped": rows_read - inserted}


async def import_from_path(
    session: AsyncSession,
    path: str,
    *,
    filters: PuzzleImportFilters,
    publish: bool = False,
    batch_size: int = 1000,
    on_progress: Optional[ProgressCb] = None,
) -> dict:
    stream = open_text_stream_from_path(path)
    try:
        return await import_from_text_stream(
            session, stream, filters=filters, publish=publish,
            batch_size=batch_size, on_progress=on_progress,
        )
    finally:
        stream.close()


async def download_to_temp(url: str, dest_path: str, *, chunk_size: int = 1 << 20) -> None:
    """Stream a remote dump to `dest_path` in chunks (never loads it all into RAM)."""
    import httpx

    # No read timeout — the dump is large and the worker job has its own timeout.
    timeout = httpx.Timeout(60.0, read=None)
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            with open(dest_path, "wb") as fh:
                async for chunk in resp.aiter_bytes(chunk_size):
                    fh.write(chunk)
    logger.info(f"download_to_temp: fetched {url} → {dest_path}")
