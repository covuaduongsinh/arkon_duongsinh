"""Chess study sets router — curated collections of games/puzzles/positions.

Reading requires chess:read; creating/curating requires chess:coach (coaches
build teaching material). Scope filtering reuses the chess permission engine.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ChessStudyItem, ChessStudySet, Employee
from app.database import get_db
from app.services import chess_service
from app.services.audit_service import log_audit
from app.services.auth_service import require_permission
from app.services.permission_engine import _get_user_permissions, can_access_chess
from app.utils.text import slugify

router = APIRouter()


def _require_coach(user: Employee) -> None:
    if user.role != "admin" and "chess:coach" not in _get_user_permissions(user):
        raise HTTPException(403, "Curating study sets requires chess:coach")


class StudySetSummary(BaseModel):
    id: uuid.UUID
    slug: Optional[str] = None
    title: str
    description: Optional[str] = None
    kind: str
    wiki_slug: Optional[str] = None
    scope_type: str = "global"
    scope_id: Optional[uuid.UUID] = None
    item_count: Optional[int] = None
    created_at: str

    model_config = {"from_attributes": True}


class StudyItem(BaseModel):
    id: uuid.UUID
    position: int
    item_type: str
    game_id: Optional[uuid.UUID] = None
    puzzle_id: Optional[uuid.UUID] = None
    fen_id: Optional[uuid.UUID] = None
    note: Optional[str] = None

    model_config = {"from_attributes": True}


class StudySetDetail(StudySetSummary):
    items: list[StudyItem] = []


class CreateStudySetBody(BaseModel):
    title: str
    description: Optional[str] = None
    kind: str = "mixed"
    wiki_slug: Optional[str] = None
    scope_type: str = "global"
    scope_id: Optional[uuid.UUID] = None


class AddItemBody(BaseModel):
    item_type: str  # game | puzzle | fen
    game_id: Optional[uuid.UUID] = None
    puzzle_id: Optional[uuid.UUID] = None
    fen_id: Optional[uuid.UUID] = None
    note: Optional[str] = None


def _summary(s: ChessStudySet) -> StudySetSummary:
    return StudySetSummary(
        id=s.id, slug=s.slug, title=s.title, description=s.description, kind=s.kind,
        wiki_slug=s.wiki_slug, scope_type=s.scope_type, scope_id=s.scope_id,
        created_at=s.created_at.isoformat(),
    )


@router.get("/chess/study-sets")
async def list_study_sets(
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:read"),
):
    sets = await chess_service.list_study_sets(db, user)
    return {"items": [_summary(s) for s in sets]}


@router.post("/chess/study-sets")
async def create_study_set(
    body: CreateStudySetBody,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:create"),
):
    _require_coach(user)
    try:
        study = await chess_service.create_study_set(
            db, user,
            title=body.title, description=body.description, kind=body.kind,
            wiki_slug=body.wiki_slug, scope_type=body.scope_type, scope_id=body.scope_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    await log_audit(db, user, "create", "chess_study_set", str(study.id))
    # Auto-index into the knowledge search pool (verbatim, no LLM).
    source = await chess_service.index_chess_study_set(db, user, study)
    await db.commit()
    await chess_service.enqueue_chess_index(db, source)
    return _summary(study)


@router.get("/chess/study-sets/{set_id}")
async def get_study_set(
    set_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:read"),
):
    study = await chess_service.get_study_set(db, set_id)
    if not study:
        raise HTTPException(404, "Study set not found")
    if not can_access_chess(user, study, "read"):
        raise HTTPException(403, "Access denied")
    detail = StudySetDetail(**_summary(study).model_dump())
    detail.items = [StudyItem.model_validate(i) for i in study.items]
    detail.item_count = len(study.items)
    return detail


@router.post("/chess/study-sets/{set_id}/items")
async def add_item(
    set_id: uuid.UUID,
    body: AddItemBody,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:create"),
):
    _require_coach(user)
    study = await chess_service.get_study_set(db, set_id)
    if not study:
        raise HTTPException(404, "Study set not found")
    if not can_access_chess(user, study, "edit"):
        raise HTTPException(403, "Access denied")
    try:
        item = await chess_service.add_study_item(
            db, study,
            item_type=body.item_type, game_id=body.game_id,
            puzzle_id=body.puzzle_id, fen_id=body.fen_id, note=body.note,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    await log_audit(db, user, "update", "chess_study_set", str(set_id))
    # Re-index so the new item's note is reflected in knowledge search.
    source = await chess_service.index_chess_study_set(db, user, study)
    await db.commit()
    await chess_service.enqueue_chess_index(db, source)
    return StudyItem.model_validate(item)


@router.post("/chess/study-sets/{set_id}/publish-wiki")
async def publish_study_set_wiki(
    set_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:create"),
):
    """Propose a companion wiki page for this study set (goes to the review queue)."""
    _require_coach(user)
    study = await chess_service.get_study_set(db, set_id)
    if not study:
        raise HTTPException(404, "Study set not found")
    if not can_access_chess(user, study, "edit"):
        raise HTTPException(403, "Access denied")

    slug = f"chess-{slugify(study.title)}".strip("-") or f"chess-study-{study.id.hex[:8]}"
    notes = [i.note for i in study.items if i.note]
    content_md = chess_service.build_study_set_markdown(
        study.title, study.description, study.kind, notes,
    )
    try:
        draft = await chess_service.propose_chess_wiki_page(
            db, user,
            slug=slug, title=study.title, content_md=content_md,
            kt_slug=chess_service.study_kind_kt_slug(study.kind),
            scope_type=study.scope_type, scope_id=study.scope_id,
            note=f"Companion wiki page for study set '{study.title}'",
        )
    except ValueError as e:
        raise HTTPException(409, str(e))
    study.wiki_slug = slug  # optimistic link; the page is created on approval
    await log_audit(db, user, "create", "wiki_draft", str(draft.id), reason="study set → wiki draft")
    await db.commit()
    return {"draft_id": str(draft.id), "slug": slug, "status": "pending_review"}


@router.delete("/chess/study-sets/{set_id}")
async def delete_study_set(
    set_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:delete"),
):
    study = await chess_service.get_study_set(db, set_id)
    if not study:
        raise HTTPException(404, "Study set not found")
    if not can_access_chess(user, study, "delete"):
        raise HTTPException(403, "Access denied")
    await chess_service.delete_study_set(db, study)
    await log_audit(db, user, "delete", "chess_study_set", str(set_id))
    await db.commit()
    return {"deleted": True}
