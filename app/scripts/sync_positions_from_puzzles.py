"""Project chess_puzzles into the chess_positions library (idempotent).

Each puzzle becomes/refreshes one position linked by source_puzzle_id; the
puzzle keeps the solution (read via the link, never copied). Safe to re-run —
existing rows are updated in place, boards already in the library aren't
duplicated. Usually triggered by `import_lichess_puzzles --sync`, but run it
standalone to (re)sync after editing puzzles.

Usage:
    python -m app.scripts.sync_positions_from_puzzles            # all puzzles, global
    python -m app.scripts.sync_positions_from_puzzles --only-lichess --limit 5000
"""

import argparse
import asyncio

from loguru import logger

from app.database import async_session_factory
from app.services import chess_service


async def run(args) -> None:
    async with async_session_factory() as session:
        stats = await chess_service.sync_positions_from_puzzles(
            session,
            scope_type="global",
            only_lichess=args.only_lichess,
            limit=args.limit,
            on_progress=lambda done, total: logger.info(f"sync … {done}/{total}"),
        )
        await session.commit()
    logger.success(
        f"Sync done over {stats['total_puzzles']} puzzles: "
        f"+{stats['created']} created, ~{stats['updated']} refreshed, "
        f"{stats['skipped']} skipped (board already present)."
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Sync puzzles → position library.")
    p.add_argument("--only-lichess", action="store_true", help="Only sync source='lichess' puzzles")
    p.add_argument("--limit", type=int, default=None, help="Max puzzles to process")
    asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    main()
