"""DEMO: show the Chess ↔ Knowledge linkage end-to-end (Phase 1).

Drives the REAL services (no HTTP) and prints the linkage chain so you can see:
  1. Creating a chess lesson / study set auto-creates a verbatim `Source`
     (tagged with a chess sub-topic knowledge type) → searchable knowledge.
  2. "Publish to wiki" creates a review-gated WikiPageDraft + an optimistic
     forward link (lesson.wiki_slug → wiki page).
  3. The wiki page's chess-links endpoint resolves BACK to the lesson/study set
     and the chess Sources that fed it (two-way linkage).

Run against a THROWAWAY DB (migration 042 applied). Safe & idempotent-ish:
    python -m app.scripts.demo_chess_link
"""

import asyncio

from sqlalchemy import select

from app.database import async_session_factory
from app.database.models import (
    ChessLesson,
    ChessStudySet,
    Employee,
    KnowledgeType,
    Source,
    WikiPage,
)
from app.services import chess_lms_service as lms
from app.services import chess_service


def hr(title: str) -> None:
    print("\n" + "=" * 72 + f"\n{title}\n" + "=" * 72)


async def _source_line(session, source_id) -> str:
    src = await session.get(Source, source_id)
    kt = await session.get(KnowledgeType, src.knowledge_type_id) if src.knowledge_type_id else None
    return (
        f"Source[{str(src.id)[:8]}]  type={src.source_type:<12} "
        f"verbatim={src.preserve_verbatim}  kt={kt.slug if kt else None}  "
        f"status={src.status}\n      title={src.title!r}"
    )


async def main() -> None:
    async with async_session_factory() as session:
        admin = Employee(name="Demo Coach", email="demo-coach@example.com",
                         role="admin", global_role="admin")
        session.add(admin)
        await session.commit()

        hr("0) Chess knowledge-type family (taxonomy seeded by migration 042)")
        fam = await chess_service.chess_family_kt_slugs(session)
        print("chess_family_kt_slugs() =", fam)

        # ── 1) Lesson → auto-indexed verbatim Source ──────────────────────────
        hr("1) Create a class + lesson  →  auto-indexed into knowledge search")
        cls = await lms.create_class(session, admin, name="CLB Cờ vua — Lớp nâng cao")
        lesson = await lms.create_lesson(
            session, admin, cls,
            title="Tàn cuộc Vua và Tốt: luật ô vuông",
            content_md=(
                "# Luật ô vuông\n\n"
                "Khi chỉ còn Vua đối Tốt, dùng 'ô vuông' để biết Vua có kịp bắt "
                "Tốt thông hay không. Nếu Vua đối phương nằm trong ô vuông của Tốt, "
                "Vua kịp bắt; nếu không, Tốt phong hậu.\n"
            ),
        )
        source = await chess_service.index_chess_lesson(session, admin, cls, lesson)
        await session.commit()
        print(f"Lesson[{str(lesson.id)[:8]}]  title={lesson.title!r}")
        print(f"  lesson.indexed_source_id → {str(lesson.indexed_source_id)[:8]}  (forward link)")
        print("  " + await _source_line(session, source.id))

        # ── 2) Study set (+ item note) → auto-indexed verbatim Source ─────────
        hr("2) Create a study set with a coach note  →  auto-indexed")
        study = await chess_service.create_study_set(
            session, admin, title="Bộ tàn cuộc Vua-Tốt cơ bản",
            description="Tuyển tập thế tàn cuộc Vua và Tốt cho học viên.",
            kind="endgame",
        )
        await chess_service.add_study_item(
            session, study, item_type="fen",
            note="Thế then chốt: đẩy Tốt thông, Vua tiến lên yểm trợ phong hậu.",
        )
        s2 = await chess_service.index_chess_study_set(session, admin, study)
        await session.commit()
        print(f"StudySet[{str(study.id)[:8]}]  title={study.title!r}  kind={study.kind}")
        print(f"  → kt mapped from kind: {chess_service.study_kind_kt_slug(study.kind)}")
        print("  " + await _source_line(session, s2.id))

        # ── 3) Publish lesson → review-gated wiki draft + forward link ────────
        hr("3) Publish the lesson to wiki  →  review-gated draft (Duyệt bài)")
        slug = "chess-tan-cuoc-vua-tot-luat-o-vuong"
        draft = await chess_service.propose_chess_wiki_page(
            session, admin,
            slug=slug, title=lesson.title, content_md=lesson.content_md,
            kt_slug="chess-strategy", scope_type="global", scope_id=None,
            note="Companion wiki page for lesson",
        )
        lesson.wiki_slug = slug  # optimistic forward link (as the endpoint does)
        await session.commit()
        print(f"WikiPageDraft[{str(draft.id)[:8]}]  kind={draft.draft_kind}  "
              f"status={draft.status}  → in review queue")
        print(f"  suggested_metadata = {draft.suggested_metadata}")
        print(f"  lesson.wiki_slug now → {lesson.wiki_slug!r}  (chess → wiki forward link)")

        # ── 4) Simulate reviewer approval: materialise the wiki page ──────────
        hr("4) Reviewer approves  →  wiki page exists, fed by the chess Source")
        page = WikiPage(
            slug=slug, title=lesson.title, status="seed",
            content_md=lesson.content_md, scope_type="global",
            knowledge_type_slugs=["chess-strategy"],
            source_ids=[source.id],  # the lesson's verbatim Source fed this page
            version=1,
        )
        session.add(page)
        await session.commit()
        print(f"WikiPage[{str(page.id)[:8]}]  slug={page.slug!r}  "
              f"kt={page.knowledge_type_slugs}  source_ids={[str(i)[:8] for i in page.source_ids]}")

        # ── 5) Wiki → chess backlink (the /wiki/chess-links/{slug} payload) ───
        hr("5) Wiki page → chess-links  (GET /api/wiki/chess-links/{slug})")
        # Also point the study set at the same page to show it surfaces too.
        study.wiki_slug = slug
        await session.commit()

        linked_lessons = (await session.execute(
            select(ChessLesson.id, ChessLesson.title).where(ChessLesson.wiki_slug == slug)
        )).all()
        linked_sets = (await session.execute(
            select(ChessStudySet.id, ChessStudySet.title, ChessStudySet.kind)
            .where(ChessStudySet.wiki_slug == slug)
        )).all()
        page2 = await session.get(WikiPage, page.id)
        chess_sources = (await session.execute(
            select(Source.id, Source.title, Source.source_type).where(
                Source.id.in_(list(page2.source_ids)),
                Source.source_type.like("chess_%"),
            )
        )).all()

        print(f"For wiki page {slug!r}:")
        print("  lessons   →", [(str(i)[:8], t) for i, t, in linked_lessons])
        print("  studySets →", [(str(i)[:8], t, k) for i, t, k in linked_sets])
        print("  sources   →", [(str(i)[:8], st, t) for i, t, st in chess_sources])

        hr("KẾT QUẢ: liên kết hai chiều Cờ vua ↔ Tri thức đã hoạt động")
        print("chess → wiki : lesson.wiki_slug / study_set.wiki_slug  +  draft (qua Duyệt bài)")
        print("wiki → chess : /wiki/chess-links/{slug} trả lesson + study set + Source")
        print("search       : mỗi lesson/study set có 1 verbatim Source (chess KT) → vào pool")
        print("               tìm kiếm tri thức; có embedding model thì search_wiki trả luôn.")


if __name__ == "__main__":
    asyncio.run(main())
