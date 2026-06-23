"""Seed chess wiki DRAFTS from a curriculum outline using the configured LLM.

For each topic in the outline this script asks the active LLM to write a chess
knowledge page (Vietnamese), then files it as a review-gated WikiPageDraft via
`chess_service.propose_chess_wiki_page`. Nothing is published directly — every
generated page lands in the "Duyệt bài" queue for a teacher/editor to refine and
approve. This is the AI-assisted seeding path (one of three: AI / manual / import).

Idempotent: a topic is skipped when a wiki page with its slug already exists, or
when a pending/needs_revision create-draft for that slug is already queued.

Usage (inside the api/worker container):
    docker compose exec -T api python -m app.scripts.seed_chess_wiki_from_curriculum
    docker compose exec -T api python -m app.scripts.seed_chess_wiki_from_curriculum path/to/outline.json

Outline JSON format (optional — a built-in default is used when omitted):
    [
      {"title": "Khai cuộc Ý", "slug": "khai-cuoc-y",
       "kt_slug": "chess-opening", "hint": "1.e4 e5 2.Nf3 Nc6 3.Bc4 ..."},
      ...
    ]
"""

import asyncio
import json
import sys
from pathlib import Path

from loguru import logger
from sqlalchemy import select

from app.database import async_session_factory
from app.database.models import Employee, WikiPage, WikiPageDraft
from app.services import chess_service, wiki_service

# Knowledge-type slugs that are valid here (the chess family, migration 042).
VALID_KT = {"chess", "chess-opening", "chess-tactics", "chess-endgame", "chess-strategy", "chess-game"}

# Curated chess glossary used by default — a stable set of concept pages with
# canonical slugs + VN/EN aliases, so generated wikilinks have real destinations.
DEFAULT_OUTLINE_PATH = Path(__file__).with_name("data") / "chess_glossary_outline.json"

# Built-in starter curriculum — a teacher can replace it with a JSON file.
DEFAULT_OUTLINE: list[dict] = [
    {"title": "Nguyên tắc khai cuộc cơ bản", "slug": "nguyen-tac-khai-cuoc-co-ban",
     "kt_slug": "chess-opening",
     "hint": "Kiểm soát trung tâm, phát triển quân nhẹ, nhập thành sớm, không đi một quân nhiều lần."},
    {"title": "Khai cuộc Ý (Giuoco Piano)", "slug": "khai-cuoc-y-giuoco-piano",
     "kt_slug": "chess-opening",
     "hint": "1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 — ý tưởng, kế hoạch hai bên, các bẫy thường gặp."},
    {"title": "Đòn chiến thuật: Nĩa (Fork)", "slug": "chien-thuat-nia-fork",
     "kt_slug": "chess-tactics",
     "hint": "Một quân tấn công hai mục tiêu cùng lúc; ví dụ nĩa Mã, nĩa Tốt, nĩa Hậu."},
    {"title": "Đòn chiến thuật: Ghim (Pin) và Xiên (Skewer)", "slug": "chien-thuat-ghim-xien",
     "kt_slug": "chess-tactics",
     "hint": "Phân biệt ghim tuyệt đối/tương đối và đòn xiên; cách khai thác và hoá giải."},
    {"title": "Tàn cuộc Vua và Tốt: luật ô vuông", "slug": "tan-cuoc-vua-tot-luat-o-vuong",
     "kt_slug": "chess-endgame",
     "hint": "Quy tắc ô vuông để biết Vua có kịp bắt Tốt thông; khái niệm đối mặt (opposition)."},
    {"title": "Tàn cuộc Xe cơ bản: thế Lucena và Philidor", "slug": "tan-cuoc-xe-lucena-philidor",
     "kt_slug": "chess-endgame",
     "hint": "Lucena (bên mạnh thắng nhờ 'bắc cầu'), Philidor (bên yếu thủ hoà)."},
    {"title": "Cấu trúc Tốt và kế hoạch trung cuộc", "slug": "cau-truc-tot-va-ke-hoach-trung-cuoc",
     "kt_slug": "chess-strategy",
     "hint": "Tốt cô lập, Tốt chồng, Tốt thông, lỗ hổng; cách chọn kế hoạch theo cấu trúc."},
]

SYSTEM_PROMPT = (
    "Bạn là một huấn luyện viên cờ vua giàu kinh nghiệm, soạn trang WIKI kiến thức "
    "chuyên môn bằng TIẾNG VIỆT cho giáo viên dạy cờ. Viết rõ ràng, chính xác, có cấu "
    "trúc. Dùng Markdown: bắt đầu bằng '# Tiêu đề', sau đó các mục con (##). Khi minh hoạ "
    "thế cờ, dùng khối ```fen với một FEN hợp lệ; khi minh hoạ chuỗi nước, dùng khối ```pgn. "
    "BẮT BUỘC chèn ÍT NHẤT 3 liên kết [[slug]] tới các khái niệm liên quan, và CHỈ ĐƯỢC "
    "dùng các slug có trong 'DANH SÁCH TRANG' được cung cấp — KHÔNG bịa slug mới. Dùng "
    "[[slug|chữ hiển thị tiếng Việt]] khi muốn chữ hiển thị khác slug. KHÔNG bịa nguồn, "
    "KHÔNG thêm lời chào hay phần kết thừa — chỉ nội dung trang."
)


def _build_link_menu(outline: list[dict], existing_pages: list[tuple[str, str]]) -> str:
    """Render the 'DANH SÁCH TRANG' the LLM may link to: outline slugs + already
    published chess wiki pages. Each line is `slug — title (alias, alias)`."""
    seen: set[str] = set()
    lines: list[str] = []
    for t in outline:
        slug = t.get("slug")
        if not slug or slug in seen:
            continue
        seen.add(slug)
        aliases = ", ".join(t.get("aliases") or [])
        alias_part = f" (đồng nghĩa: {aliases})" if aliases else ""
        lines.append(f"- {slug} — {t.get('title', slug)}{alias_part}")
    for slug, title in existing_pages:
        if slug in seen:
            continue
        seen.add(slug)
        lines.append(f"- {slug} — {title}")
    return "\n".join(lines)


def _build_prompt(topic: dict, link_menu: str) -> str:
    hint = topic.get("hint") or ""
    return (
        f"Soạn một trang wiki cờ vua với tiêu đề: \"{topic['title']}\".\n"
        f"Phân mục kiến thức: {topic['kt_slug']}.\n"
        f"Gợi ý nội dung cần bao quát: {hint}\n\n"
        "DANH SÁCH TRANG có thể liên kết (chỉ dùng slug bên trái cho [[...]]):\n"
        f"{link_menu}\n\n"
        "Trả về DUY NHẤT nội dung Markdown của trang (không kèm giải thích ngoài lề)."
    )


async def _already_seeded(session, slug: str) -> bool:
    """True when a page or an open create-draft already exists for this slug."""
    page = await session.execute(select(WikiPage.id).where(WikiPage.slug == slug).limit(1))
    if page.scalar_one_or_none() is not None:
        return True
    draft = await session.execute(
        select(WikiPageDraft.id).where(
            WikiPageDraft.draft_kind == "create",
            WikiPageDraft.status.in_(["pending", "needs_revision"]),
            WikiPageDraft.suggested_metadata["slug"].astext == slug,
        ).limit(1)
    )
    return draft.scalar_one_or_none() is not None


async def main() -> None:
    # Outline precedence: argv path → curated glossary JSON → built-in default.
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        with open(args[0], encoding="utf-8") as fh:
            outline = json.load(fh)
        logger.info(f"Loaded {len(outline)} topics from {args[0]}")
    elif DEFAULT_OUTLINE_PATH.exists():
        outline = json.loads(DEFAULT_OUTLINE_PATH.read_text(encoding="utf-8"))
        logger.info(f"Loaded {len(outline)} topics from {DEFAULT_OUTLINE_PATH}")
    else:
        outline = DEFAULT_OUTLINE
        logger.info(f"Using built-in default outline ({len(outline)} topics)")

    async with async_session_factory() as session:
        author = (await session.execute(
            select(Employee).where(Employee.role == "admin").order_by(Employee.created_at).limit(1)
        )).scalar_one_or_none()
        if author is None:
            logger.error("No admin employee found — create one first.")
            return

        try:
            from app.ai.registry import ProviderRegistry

            registry = ProviderRegistry(session)
            llm = await registry.get_llm()
        except Exception as e:  # noqa: BLE001
            logger.error(f"No LLM provider configured ({e}). Set one in Settings first.")
            return

        # Build the link "menu" + alias lookup once: outline slugs/aliases PLUS
        # any chess wiki pages already published. The LLM is told to link only to
        # these slugs; generated targets are then normalized + validated against
        # this same set so a stray/aliased slug can't become a dead link.
        family = await chess_service.chess_family_kt_slugs(session)
        existing_rows = (await session.execute(
            select(WikiPage.slug, WikiPage.title, WikiPage.aliases)
            .where(WikiPage.knowledge_type_slugs.overlap(family))
        )).all()
        link_menu = _build_link_menu(outline, [(r.slug, r.title) for r in existing_rows])
        alias_lookup = wiki_service.build_alias_lookup(
            [(t["slug"], t.get("aliases") or []) for t in outline]
            + [(r.slug, r.aliases or []) for r in existing_rows]
        )
        known_slugs = set(alias_lookup.values())

        created, skipped, failed = 0, 0, 0
        for topic in outline:
            slug = topic["slug"]
            kt_slug = topic.get("kt_slug", "chess")
            if kt_slug not in VALID_KT:
                logger.warning(f"[{slug}] invalid kt_slug '{kt_slug}', falling back to 'chess'")
                kt_slug = "chess"

            if await _already_seeded(session, slug):
                logger.info(f"[{slug}] already seeded — skipping")
                skipped += 1
                continue

            try:
                content_md = await llm.generate(
                    _build_prompt(topic, link_menu), system=SYSTEM_PROMPT,
                    max_tokens=2000, temperature=0.4,
                )
                content_md = (content_md or "").strip()
                if not content_md:
                    raise ValueError("LLM returned empty content")

                # Resolve alias targets → canonical slugs, then report any link
                # that still points outside the known set (likely an LLM-invented
                # slug). We keep the page but flag it for the reviewer.
                content_md = wiki_service.normalize_wikilink_targets(content_md, alias_lookup)
                unknown = [
                    t for t in wiki_service.extract_wikilinks(content_md)
                    if t not in known_slugs and t != slug
                ]
                if unknown:
                    logger.warning(f"[{slug}] {len(unknown)} unknown link target(s): {unknown}")

                draft = await chess_service.propose_chess_wiki_page(
                    session, author,
                    slug=slug, title=topic["title"], content_md=content_md,
                    kt_slug=kt_slug, scope_type="global", scope_id=None,
                    aliases=topic.get("aliases") or [],
                    note=f"Nháp do AI sinh từ giáo trình ({kt_slug}). Cần giáo viên rà soát.",
                )
                await session.commit()
                logger.success(f"[{slug}] draft {draft.id} queued for review")
                created += 1
            except Exception as e:  # noqa: BLE001 — one bad topic must not stop the rest
                await session.rollback()
                logger.error(f"[{slug}] failed: {e}")
                failed += 1

        print("\n================ SEED CHESS WIKI ================")
        print(f"Tạo nháp mới : {created}")
        print(f"Bỏ qua (đã có): {skipped}")
        print(f"Lỗi          : {failed}")
        print("Vào 'Duyệt bài' (/wiki/review) để rà soát & phê duyệt các nháp.")


if __name__ == "__main__":
    asyncio.run(main())
