"""Backfill: normalize existing wiki pages' `[[alias]]` targets to canonical slugs.

After the alias system (migration 043) lands, pages authored before it may still
carry VN/EN alias targets (e.g. `[[fork]]`) that resolve only via the alias map.
This one-shot pass rewrites them to `[[chien-thuat-nia-fork|fork]]` and rebuilds
each page's wiki_links edges so the graph + lint reflect the canonical slugs.

Idempotent: a page whose content is already canonical is left untouched.

Usage (inside the api/worker container):
    docker compose exec -T api python -m app.scripts.backfill_wikilink_aliases
    docker compose exec -T api python -m app.scripts.backfill_wikilink_aliases --dry-run
"""

import asyncio
import sys

from loguru import logger
from sqlalchemy import select

from app.database import async_session_factory
from app.database.models import WikiPage
from app.services import wiki_service


async def main() -> None:
    dry_run = "--dry-run" in sys.argv[1:]
    changed, scanned = 0, 0

    async with async_session_factory() as session:
        pages = (await session.execute(select(WikiPage))).scalars().all()
        for page in pages:
            scanned += 1
            alias_map = await wiki_service.build_alias_map(
                session, page.scope_type or "global", page.scope_id
            )
            new_md = wiki_service.normalize_wikilink_targets(page.content_md or "", alias_map)
            if new_md == (page.content_md or ""):
                continue
            changed += 1
            logger.info(f"[{page.slug}] alias targets normalized")
            if not dry_run:
                page.content_md = new_md
                await session.flush()
                await wiki_service.refresh_links(session, page.id, page.slug, new_md)
        if not dry_run:
            await session.commit()

    print("\n============ BACKFILL WIKILINK ALIASES ============")
    print(f"Đã quét : {scanned} trang")
    print(f"Cập nhật: {changed} trang" + ("  (DRY RUN — chưa ghi)" if dry_run else ""))


if __name__ == "__main__":
    asyncio.run(main())
