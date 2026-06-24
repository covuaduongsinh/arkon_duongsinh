"""Import the Lichess puzzle database (CSV) into chess_puzzles.

The Lichess puzzle dump (`lichess_db_puzzle.csv` / `.csv.zst`) has columns:

    PuzzleId,FEN,Moves,Rating,RatingDeviation,Popularity,NbPlays,Themes,GameUrl,OpeningTags

Each row lands as one ChessPuzzle (source='lichess', slug='lichess-<id>',
deduped on `lichess_id` via ON CONFLICT DO NOTHING). The full dump is ~4–5M
rows — do NOT import it all into an on-prem Postgres; always filter with
--limit / --min-rating / --theme / --opening.

After import you usually want the position library populated too: pass --sync
(or run app/scripts/sync_positions_from_puzzles.py) to project the imported
puzzles into chess_positions.

Usage:
    python -m app.scripts.import_lichess_puzzles path/to/lichess_db_puzzle.csv \
        --limit 5000 --min-rating 1200 --max-rating 2200 --sync

Reads .csv directly, or .csv.zst when the `zstandard` package is installed.
"""

import argparse
import asyncio
import csv
import io
import sys

from loguru import logger
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import async_session_factory
from app.database.models import ChessPuzzle
from app.services import chess_service


def _open_csv(path: str):
    """Yield a text stream for a .csv or .csv.zst file."""
    if path.endswith(".zst"):
        try:
            import zstandard
        except ImportError as e:
            raise SystemExit(
                "Reading .zst needs the 'zstandard' package: pip install zstandard "
                "(or decompress first: zstd -d lichess_db_puzzle.csv.zst)"
            ) from e
        fh = open(path, "rb")
        reader = zstandard.ZstdDecompressor().stream_reader(fh)
        return io.TextIOWrapper(reader, encoding="utf-8", newline="")
    return open(path, "r", encoding="utf-8", newline="")


def _to_int(value: str):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _opening_name(opening_tags: str):
    """Lichess OpeningTags → a readable opening name. Tags are space-separated,
    each underscore-joined; we take the most specific (last) and unslug it."""
    tags = (opening_tags or "").split()
    if not tags:
        return None
    return tags[-1].replace("_", " ").replace("-", " ")


def _row_to_values(row: dict) -> dict | None:
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


def _passes_filters(row: dict, args) -> bool:
    rating = _to_int(row.get("Rating"))
    if args.min_rating is not None and (rating is None or rating < args.min_rating):
        return False
    if args.max_rating is not None and (rating is None or rating > args.max_rating):
        return False
    if args.theme and args.theme.lower() not in (row.get("Themes") or "").lower():
        return False
    if args.opening and args.opening.lower() not in (row.get("OpeningTags") or "").lower():
        return False
    return True


async def _insert_batch(session, batch: list[dict]) -> int:
    if not batch:
        return 0
    stmt = pg_insert(ChessPuzzle).values(batch)
    # Dedupe re-imports on the unique lichess_id index.
    stmt = stmt.on_conflict_do_nothing(index_elements=["lichess_id"])
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount or 0


async def run(args) -> None:
    if args.publish:
        logger.info("Imported puzzles will be published (visible to students).")

    inserted = considered = 0
    batch: list[dict] = []
    stream = _open_csv(args.csv_path)
    try:
        reader = csv.DictReader(stream)
        async with async_session_factory() as session:
            for row in reader:
                if args.limit and considered >= args.limit:
                    break
                if not _passes_filters(row, args):
                    continue
                values = _row_to_values(row)
                if values is None:
                    continue
                if args.publish:
                    values["is_published"] = True
                batch.append(values)
                considered += 1
                if len(batch) >= args.batch_size:
                    inserted += await _insert_batch(session, batch)
                    batch = []
                    logger.info(f"… {considered} read, {inserted} inserted")
            inserted += await _insert_batch(session, batch)
    finally:
        stream.close()

    logger.success(
        f"Import done: {considered} rows matched, {inserted} new puzzles "
        f"(skipped {considered - inserted} duplicates)."
    )

    if args.sync:
        async with async_session_factory() as session:
            stats = await chess_service.sync_positions_from_puzzles(
                session, scope_type="global", only_lichess=True,
                on_progress=lambda done, total: logger.info(f"sync … {done}/{total}"),
            )
            await session.commit()
        logger.success(
            f"Sync done: +{stats['created']} positions, "
            f"~{stats['updated']} refreshed, {stats['skipped']} skipped."
        )


def main() -> None:
    p = argparse.ArgumentParser(description="Import Lichess puzzle CSV into chess_puzzles.")
    p.add_argument("csv_path", help="Path to lichess_db_puzzle.csv or .csv.zst")
    p.add_argument("--limit", type=int, default=None, help="Max rows to import (after filters)")
    p.add_argument("--min-rating", type=int, default=None)
    p.add_argument("--max-rating", type=int, default=None)
    p.add_argument("--theme", default=None, help="Substring filter on Themes")
    p.add_argument("--opening", default=None, help="Substring filter on OpeningTags")
    p.add_argument("--batch-size", type=int, default=1000)
    p.add_argument("--publish", action="store_true", help="Mark imported puzzles published")
    p.add_argument("--sync", action="store_true", help="Sync into chess_positions after import")
    args = p.parse_args()

    if not args.limit and not (args.min_rating or args.max_rating or args.theme or args.opening):
        logger.warning(
            "No --limit or filters set — this would import the ENTIRE Lichess dump "
            "(~5M rows). Aborting. Add --limit or a rating/theme filter."
        )
        sys.exit(2)

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
