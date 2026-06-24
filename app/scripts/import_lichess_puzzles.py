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

Reads .csv directly, or .csv.zst (the `zstandard` package is a declared dep).

The actual parsing/filtering/insert logic lives in app.services.puzzle_import_service
so the CLI, the web API and the arq worker all share one implementation.
"""

import argparse
import asyncio
import sys

from loguru import logger

from app.database import async_session_factory
from app.services import chess_service
from app.services.puzzle_import_service import (
    PuzzleImportFilters,
    import_from_path,
    validate_filters,
)


async def run(args) -> None:
    if args.publish:
        logger.info("Imported puzzles will be published (visible to students).")

    filters = PuzzleImportFilters(
        min_rating=args.min_rating,
        max_rating=args.max_rating,
        theme=args.theme,
        opening=args.opening,
        limit=args.limit,
    )

    async with async_session_factory() as session:
        stats = await import_from_path(
            session, args.csv_path,
            filters=filters, publish=args.publish, batch_size=args.batch_size,
            on_progress=lambda read, ins: logger.info(f"… {read} read, {ins} inserted"),
        )

    logger.success(
        f"Import done: {stats['rows_read']} rows matched, {stats['inserted']} new puzzles "
        f"(skipped {stats['skipped']} duplicates)."
    )

    if args.sync:
        async with async_session_factory() as session:
            sync_stats = await chess_service.sync_positions_from_puzzles(
                session, scope_type="global", only_lichess=True,
                on_progress=lambda done, total: logger.info(f"sync … {done}/{total}"),
            )
            await session.commit()
        logger.success(
            f"Sync done: +{sync_stats['created']} positions, "
            f"~{sync_stats['updated']} refreshed, {sync_stats['skipped']} skipped."
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

    try:
        validate_filters(PuzzleImportFilters(
            min_rating=args.min_rating, max_rating=args.max_rating,
            theme=args.theme, opening=args.opening, limit=args.limit,
        ))
    except ValueError as e:
        logger.warning(str(e))
        sys.exit(2)

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
