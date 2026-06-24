"""DEMO: trải nghiệm các tính năng wikilink mới (alias VN/EN + lesson↔wiki).

Dựng một bộ dữ liệu mẫu NHỎ, idempotent, gắn nhãn "DEMO" để dễ tìm/xoá:

  1. Hai trang khái niệm cờ vua CÓ ALIAS:
       - chien-thuat-nia-fork      (alias: fork, nĩa, nia, đòn nĩa)
       - khai-niem-doi-mat-opposition (alias: opposition, đối mặt)
  2. Một trang DEMO cố tình viết link bằng TỪ ĐỒNG NGHĨA:
       [[fork]], [[nĩa|đòn nĩa]], [[opposition]]
     → sau khi lưu, hệ thống TỰ chuẩn hoá về slug chuẩn (xem mã nguồn trang
       sẽ thấy [[chien-thuat-nia-fork|fork]] …) và link trỏ đúng.
  3. Một lớp + bài giảng DEMO tham chiếu [[chien-thuat-nia-fork]] trong nội dung
     → trang khái niệm "Nĩa" sẽ hiện bài giảng này ở mục "Bài giảng nhắc tới"
       (khối "Nội dung cờ vua liên quan").

Chạy (trong container api):
    docker compose exec -T api python -m app.scripts.demo_wikilink_features
Xoá dữ liệu demo:
    docker compose exec -T api python -m app.scripts.demo_wikilink_features --cleanup

Không cần worker/queue — demo chỉ dùng trang wiki + cạnh liên kết.
"""

import asyncio
import sys

from loguru import logger
from sqlalchemy import delete, select

from app.database import async_session_factory
from app.database.models import (
    ChessClass,
    ChessLesson,
    ChessLessonLink,
    Employee,
)
from app.services import chess_lms_service as lms
from app.services import chess_service, wiki_service

DEMO_CLASS_NAME = "DEMO · Lớp cờ vua (wikilink)"
DEMO_PAGE_SLUG = "demo-wikilink-alias"

# (slug, title, kt_slug, aliases, content_md)
GLOSSARY = [
    (
        "chien-thuat-nia-fork",
        "Đòn chiến thuật: Nĩa (Fork)",
        "chess-tactics",
        ["fork", "nĩa", "nia", "đòn nĩa"],
        "# Đòn chiến thuật: Nĩa (Fork)\n\n"
        "**Nĩa** là đòn trong đó một quân tấn công đồng thời hai (hoặc nhiều) mục "
        "tiêu, đối phương không thể cứu cả hai. Mã là quân nĩa hiệu quả nhất.\n\n"
        "Trong tàn cuộc, nĩa thường kết hợp với thế [[opposition]] để thắng.\n",
    ),
    (
        "khai-niem-doi-mat-opposition",
        "Khái niệm Đối mặt (Opposition)",
        "chess-endgame",
        ["opposition", "đối mặt"],
        "# Khái niệm Đối mặt (Opposition)\n\n"
        "**Đối mặt** là khi hai Vua đứng đối diện, cách nhau một ô; bên KHÔNG phải "
        "đi sẽ giành được ô tới hạn. Đây là chìa khoá của tàn cuộc Vua–Tốt.\n",
    ),
]

DEMO_PAGE = (
    DEMO_PAGE_SLUG,
    "DEMO · Trang minh hoạ alias wikilink",
    "chess",
    "# DEMO · Trang minh hoạ alias wikilink\n\n"
    "Trang này CỐ TÌNH viết wikilink bằng từ đồng nghĩa để minh hoạ chuẩn hoá "
    "alias. Sau khi lưu, các link dưới đây tự trỏ về slug chuẩn:\n\n"
    "- Tiếng Anh: [[fork]]\n"
    "- Tiếng Việt + chữ hiển thị: [[nĩa|đòn nĩa]]\n"
    "- Tàn cuộc: [[opposition]]\n\n"
    "Mở chế độ sửa trang để thấy nội dung đã thành "
    "`[[chien-thuat-nia-fork|fork]]` …\n",
)


async def _admin(session) -> Employee | None:
    return (await session.execute(
        select(Employee).where(Employee.role == "admin").order_by(Employee.created_at).limit(1)
    )).scalar_one_or_none()


async def seed() -> None:
    async with async_session_factory() as session:
        admin = await _admin(session)
        if admin is None:
            logger.error("Không tìm thấy admin — tạo một tài khoản admin trước.")
            return

        # 1) Trang khái niệm CÓ alias (tạo trước để alias map có dữ liệu chuẩn hoá).
        for slug, title, kt, aliases, body in GLOSSARY:
            await wiki_service.upsert_page(
                session, slug=slug, title=title, page_type="concept",
                content_md=body, summary=title,
                knowledge_type_slugs=[kt], source_ids=[],
                scope_type="global", scope_id=None, status="developing",
                aliases=aliases,
            )
        await session.flush()

        # 2) Trang DEMO dùng alias — upsert sẽ normalize [[fork]]→[[chien-thuat-nia-fork|fork]].
        slug, title, kt, body = DEMO_PAGE
        await wiki_service.upsert_page(
            session, slug=slug, title=title, page_type="concept",
            content_md=body, summary="Minh hoạ chuẩn hoá alias wikilink",
            knowledge_type_slugs=[kt], source_ids=[],
            scope_type="global", scope_id=None, status="developing",
        )

        # 3) Lớp + bài giảng DEMO tham chiếu [[chien-thuat-nia-fork]] → cạnh lesson↔wiki.
        cls = (await session.execute(
            select(ChessClass).where(ChessClass.name == DEMO_CLASS_NAME).limit(1)
        )).scalar_one_or_none()
        if cls is None:
            cls = await lms.create_class(session, admin, name=DEMO_CLASS_NAME,
                                         description="Lớp mẫu cho demo wikilink.")
        lesson = (await session.execute(
            select(ChessLesson).where(
                ChessLesson.class_id == cls.id,
                ChessLesson.title == "DEMO · Bài giảng về Nĩa",
            ).limit(1)
        )).scalar_one_or_none()
        if lesson is None:
            lesson = await lms.create_lesson(
                session, admin, cls,
                title="DEMO · Bài giảng về Nĩa",
                content_md=(
                    "# Bài giảng về Nĩa\n\n"
                    "Bài này dạy đòn [[chien-thuat-nia-fork]] (còn gọi là [[fork]]).\n"
                ),
            )
        else:
            lesson.content_md = (
                "# Bài giảng về Nĩa\n\n"
                "Bài này dạy đòn [[chien-thuat-nia-fork]] (còn gọi là [[fork]]).\n"
            )
        await session.flush()
        await chess_service.refresh_lesson_links(session, lesson)

        await session.commit()

    base = "https://app.covuaduongsinh.com"
    print("\n================ DEMO WIKILINK ĐÃ SẴN SÀNG ================")
    print("Mở các URL sau để trải nghiệm:\n")
    print(f"1) Chuẩn hoá alias:  {base}/wiki/{DEMO_PAGE_SLUG}")
    print("   → 3 link đều bấm được; mở 'Sửa' để thấy đã thành [[chien-thuat-nia-fork|fork]] …\n")
    print(f"2) Bài giảng nhắc tới + backlinks: {base}/wiki/chien-thuat-nia-fork")
    print("   → khối 'Nội dung cờ vua liên quan' có 'Bài giảng nhắc tới: DEMO · Bài giảng về Nĩa';")
    print("     backlinks có 'DEMO · Trang minh hoạ alias' và trang Đối mặt.\n")
    print("3) Autocomplete khớp alias: vào trình soạn thảo wiki, gõ '[[fork' →")
    print("   gợi ý hiện trang 'Đòn chiến thuật: Nĩa (Fork)'.\n")
    print("Xoá demo: thêm cờ --cleanup khi chạy lại script này.")


async def cleanup() -> None:
    async with async_session_factory() as session:
        # Xoá MỌI lớp có tên bắt đầu "DEMO" (cascade bài giảng + chess_lesson_links).
        # Khớp theo tiền tố ASCII để vẫn bắt được cả bản ghi bị hỏng font (mojibake).
        classes = (await session.execute(
            select(ChessClass).where(ChessClass.name.like("DEMO%"))
        )).scalars().all()
        for cls in classes:
            lesson_ids = (await session.execute(
                select(ChessLesson.id).where(ChessLesson.class_id == cls.id)
            )).scalars().all()
            if lesson_ids:
                await session.execute(
                    delete(ChessLessonLink).where(ChessLessonLink.lesson_id.in_(lesson_ids))
                )
            await session.delete(cls)
        # Xoá trang DEMO + hai trang khái niệm (slug ASCII) để re-seed lại sạch.
        for slug in (DEMO_PAGE_SLUG, "chien-thuat-nia-fork", "khai-niem-doi-mat-opposition"):
            page = await wiki_service.get_page_by_slug(session, slug)
            if page is not None:
                await wiki_service.delete_page_cascade(session, page)
        await session.commit()
    print("Đã xoá dữ liệu DEMO (lớp DEMO%, bài giảng, trang demo + 2 trang khái niệm).")
    print("Chạy lại không kèm --cleanup để tạo lại bản đúng UTF-8.")


async def main() -> None:
    if "--cleanup" in sys.argv[1:]:
        await cleanup()
    else:
        await seed()


if __name__ == "__main__":
    asyncio.run(main())
