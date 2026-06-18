"""Seed a small, clearly-labelled DEMO of the Chess ↔ Knowledge linkage.

Idempotent: re-running does nothing if the demo class already exists. Creates,
under the first admin account:
  • a chess class + lesson  → auto-indexed verbatim Source (chess-strategy)
  • a study set + a noted item → auto-indexed verbatim Source (chess-endgame)
  • an (already-approved) companion wiki page linked to BOTH, fed by the lesson
    Source — so the wiki page's "Nội dung cờ vua liên quan" block is populated.

Run inside the api/worker container:
    docker compose exec -T api python -m app.scripts.demo_chess_link_seed
"""

import asyncio

from loguru import logger
from sqlalchemy import select

from app.database import async_session_factory
from app.database.models import ChessClass, Employee, WikiPage
from app.services import chess_lms_service as lms
from app.services import chess_service

DEMO_CLASS = "Demo: Liên kết Cờ vua ↔ Tri thức"
DEMO_WIKI_SLUG = "chess-demo-tan-cuoc-vua-tot"


async def main() -> None:
    async with async_session_factory() as session:
        admin = (await session.execute(
            select(Employee).where(Employee.role == "admin").order_by(Employee.created_at).limit(1)
        )).scalar_one_or_none()
        if admin is None:
            logger.error("No admin employee found — create one first.")
            return

        exists = (await session.execute(
            select(ChessClass).where(ChessClass.name == DEMO_CLASS)
        )).scalar_one_or_none()
        if exists is not None:
            logger.info(f"Demo already seeded (class {exists.id}). Wiki slug: {DEMO_WIKI_SLUG}")
            print(f"\nĐã có dữ liệu demo. Trang wiki: /wiki/{DEMO_WIKI_SLUG}")
            return

        # 1) Class + lesson → auto-indexed verbatim Source.
        cls = await lms.create_class(session, admin, name=DEMO_CLASS,
                                     description="Lớp demo cho tính năng liên kết.")
        lesson = await lms.create_lesson(
            session, admin, cls,
            title="Tàn cuộc Vua và Tốt: luật ô vuông",
            content_md=(
                "# Luật ô vuông (the rule of the square)\n\n"
                "Khi chỉ còn Vua đối Tốt thông, vẽ 'ô vuông' từ Tốt tới ô phong hậu. "
                "Nếu Vua đối phương **bên trong** ô vuông (hoặc tới lượt đi được vào), "
                "Vua kịp bắt Tốt; nếu **ngoài** ô vuông, Tốt phong hậu thắng.\n\n"
                "## Ví dụ\n\n```fen\n8/8/8/8/3P4/8/8/k6K w - - 0 1\n```\n\n"
                "Tốt d4: ô vuông là d4–d8–h8–h4. Vua đen ở a1 nằm ngoài → Tốt phong hậu.\n"
            ),
        )
        lesson_source = await chess_service.index_chess_lesson(session, admin, cls, lesson)

        # 2) Study set + noted item → auto-indexed verbatim Source.
        study = await chess_service.create_study_set(
            session, admin, title="Bộ tàn cuộc Vua-Tốt cơ bản",
            description="Tuyển tập thế tàn cuộc Vua và Tốt cho học viên mới.",
            kind="endgame",
        )
        await chess_service.add_study_item(
            session, study, item_type="fen",
            note="Thế then chốt: đối mặt (opposition) để đẩy Vua đối phương lùi, rồi tiến Tốt.",
        )
        study_source = await chess_service.index_chess_study_set(session, admin, study)

        # 3) Companion wiki page (pre-approved) linked to BOTH + fed by lesson Source.
        page = WikiPage(
            slug=DEMO_WIKI_SLUG, title="Tàn cuộc Vua và Tốt", status="developing",
            summary="Lý thuyết tàn cuộc Vua–Tốt: luật ô vuông và thế đối mặt.",
            content_md=lesson.content_md, scope_type="global",
            knowledge_type_slugs=["chess-endgame", "chess-strategy"],
            source_ids=[lesson_source.id, study_source.id], version=1,
        )
        session.add(page)
        study.wiki_slug = DEMO_WIKI_SLUG
        lesson.wiki_slug = DEMO_WIKI_SLUG
        await session.commit()

        # Best-effort: enqueue embedding so the Sources become semantically searchable.
        await chess_service.enqueue_chess_index(session, lesson_source)
        await chess_service.enqueue_chess_index(session, study_source)

        logger.success("Seeded chess↔knowledge demo.")
        print("\n================ DEMO ĐÃ SẴN SÀNG ================")
        print(f"Lớp học (Cờ vua → Lớp học): {cls.id}")
        print(f"Bài giảng (Cờ vua → Lớp học → bài giảng): /chess/lessons/{lesson.id}")
        print(f"Bộ học liệu (Cờ vua → Bộ học liệu): /chess/study/{study.id}")
        print(f"Trang wiki (Tri thức → Wiki): /wiki/{DEMO_WIKI_SLUG}")
        print("Tài liệu tự sinh (Tri thức → Tài liệu): 2 nguồn 'chess_lesson' + 'chess_study'")


if __name__ == "__main__":
    asyncio.run(main())
