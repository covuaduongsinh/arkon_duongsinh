"""Chess LMS router — classes, roster, lessons, assignments, progress.

Membership-based access: members (coach/students) and admins can view a class;
coaches/admins manage it. Base gate is chess:read (view) / chess:coach (manage).
"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import (
    ChessAssignment,
    ChessClass,
    ChessLesson,
    Employee,
)
from app.services import chess_lms_service as lms
from app.services import chess_service
from app.services.audit_service import log_audit
from app.services.auth_service import require_permission
from app.services.permission_engine import _get_user_permissions
from app.utils.text import slugify

router = APIRouter()


def _require_coach(user: Employee) -> None:
    if user.role != "admin" and "chess:coach" not in _get_user_permissions(user):
        raise HTTPException(403, "Cần quyền HLV (chess:coach)")


async def _load_class_or_403(db: AsyncSession, class_id: uuid.UUID, user: Employee, *, manage: bool = False) -> ChessClass:
    cls = await lms.get_class(db, class_id)
    if not cls:
        raise HTTPException(404, "Không tìm thấy lớp")
    role = lms.class_role(user, cls)
    if role is None:
        raise HTTPException(403, "Bạn không thuộc lớp này")
    if manage and role not in ("admin", "coach"):
        raise HTTPException(403, "Chỉ HLV mới được quản lý lớp")
    return cls


# ── Schemas ──

class ClassBody(BaseModel):
    name: str
    description: Optional[str] = None


class MemberBody(BaseModel):
    email: str
    role: str = "student"


class LessonBody(BaseModel):
    title: str
    content_md: str = ""
    study_set_id: Optional[uuid.UUID] = None


class AssignmentBody(BaseModel):
    title: str
    description: Optional[str] = None
    kind: str = "puzzles"
    puzzle_ids: list[uuid.UUID] = []
    study_set_id: Optional[uuid.UUID] = None
    lesson_id: Optional[uuid.UUID] = None
    due_at: Optional[datetime] = None


def _class_summary(cls: ChessClass, role: Optional[str]) -> dict:
    students = sum(1 for m in cls.members if m.role == "student")
    return {
        "id": str(cls.id), "name": cls.name, "description": cls.description,
        "your_role": role, "student_count": students,
        "created_at": cls.created_at.isoformat(),
    }


# ── Classes ──

@router.get("/chess/classes")
async def list_classes(db: AsyncSession = Depends(get_db), user: Employee = require_permission("chess:read")):
    classes = await lms.list_classes_for_user(db, user)
    # members aren't loaded by list query; fetch counts lazily is fine for small N
    out = []
    for c in classes:
        full = await lms.get_class(db, c.id)
        out.append(_class_summary(full, lms.class_role(user, full)))
    return {"items": out}


@router.post("/chess/classes")
async def create_class(body: ClassBody, db: AsyncSession = Depends(get_db), user: Employee = require_permission("chess:coach")):
    _require_coach(user)
    cls = await lms.create_class(db, user, name=body.name, description=body.description)
    await log_audit(db, user, "create", "chess_class", str(cls.id))
    await db.commit()
    full = await lms.get_class(db, cls.id)
    return _class_summary(full, "coach")


@router.get("/chess/classes/{class_id}")
async def get_class(class_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: Employee = require_permission("chess:read")):
    cls = await _load_class_or_403(db, class_id, user)
    members = [
        {"employee_id": str(m.employee_id), "name": m.employee.name if m.employee else "?", "role": m.role}
        for m in cls.members
    ]
    return {**_class_summary(cls, lms.class_role(user, cls)), "members": members}


@router.delete("/chess/classes/{class_id}")
async def delete_class(class_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: Employee = require_permission("chess:coach")):
    cls = await _load_class_or_403(db, class_id, user, manage=True)
    await lms.delete_class(db, cls)
    await log_audit(db, user, "delete", "chess_class", str(class_id))
    await db.commit()
    return {"deleted": True}


# ── Roster ──

@router.post("/chess/classes/{class_id}/members")
async def add_member(class_id: uuid.UUID, body: MemberBody, db: AsyncSession = Depends(get_db), user: Employee = require_permission("chess:coach")):
    cls = await _load_class_or_403(db, class_id, user, manage=True)
    emp = (await db.execute(select(Employee).where(Employee.email == body.email.strip().lower()))).scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "Không tìm thấy tài khoản với email này")
    await lms.add_member(db, cls, emp.id, role=body.role if body.role in ("student", "coach") else "student")
    await db.commit()
    return {"added": str(emp.id), "name": emp.name}


@router.delete("/chess/classes/{class_id}/members/{employee_id}")
async def remove_member(class_id: uuid.UUID, employee_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: Employee = require_permission("chess:coach")):
    await _load_class_or_403(db, class_id, user, manage=True)
    await lms.remove_member(db, class_id, employee_id)
    await db.commit()
    return {"removed": True}


# ── Lessons ──

def _lesson_dto(l: ChessLesson) -> dict:
    return {
        "id": str(l.id), "class_id": str(l.class_id), "title": l.title,
        "content_md": l.content_md, "study_set_id": str(l.study_set_id) if l.study_set_id else None,
        "wiki_slug": l.wiki_slug, "position": l.position, "created_at": l.created_at.isoformat(),
    }


@router.get("/chess/classes/{class_id}/lessons")
async def list_lessons(class_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: Employee = require_permission("chess:read")):
    await _load_class_or_403(db, class_id, user)
    lessons = await lms.list_lessons(db, class_id)
    return {"items": [{"id": str(l.id), "title": l.title, "position": l.position} for l in lessons]}


@router.post("/chess/classes/{class_id}/lessons")
async def create_lesson(class_id: uuid.UUID, body: LessonBody, db: AsyncSession = Depends(get_db), user: Employee = require_permission("chess:coach")):
    cls = await _load_class_or_403(db, class_id, user, manage=True)
    lesson = await lms.create_lesson(db, user, cls, title=body.title, content_md=body.content_md, study_set_id=body.study_set_id)
    # Auto-index the lesson into the knowledge search pool (verbatim, no LLM).
    source = await chess_service.index_chess_lesson(db, user, cls, lesson)
    await db.commit()
    await chess_service.enqueue_chess_index(db, source)
    return _lesson_dto(lesson)


@router.get("/chess/lessons/{lesson_id}")
async def get_lesson(lesson_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: Employee = require_permission("chess:read")):
    lesson = await lms.get_lesson(db, lesson_id)
    if not lesson:
        raise HTTPException(404, "Không tìm thấy bài giảng")
    await _load_class_or_403(db, lesson.class_id, user)
    return _lesson_dto(lesson)


@router.post("/chess/lessons/{lesson_id}/publish-wiki")
async def publish_lesson_wiki(lesson_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: Employee = require_permission("chess:coach")):
    """Propose a companion wiki page from this lesson (goes to the review queue)."""
    lesson = await lms.get_lesson(db, lesson_id)
    if not lesson:
        raise HTTPException(404, "Không tìm thấy bài giảng")
    cls = await _load_class_or_403(db, lesson.class_id, user, manage=True)
    slug = f"chess-{slugify(lesson.title)}".strip("-") or f"chess-lesson-{lesson.id.hex[:8]}"
    content_md = (lesson.content_md or "").strip() or chess_service.build_lesson_markdown(lesson.title, "")
    try:
        draft = await chess_service.propose_chess_wiki_page(
            db, user,
            slug=slug, title=lesson.title, content_md=content_md,
            kt_slug="chess-strategy",
            scope_type=cls.scope_type, scope_id=cls.scope_id,
            note=f"Companion wiki page for lesson '{lesson.title}'",
        )
    except ValueError as e:
        raise HTTPException(409, str(e))
    lesson.wiki_slug = slug  # optimistic link; the page is created on approval
    await log_audit(db, user, "create", "wiki_draft", str(draft.id), reason="lesson → wiki draft")
    await db.commit()
    return {"draft_id": str(draft.id), "slug": slug, "status": "pending_review"}


@router.delete("/chess/lessons/{lesson_id}")
async def delete_lesson(lesson_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: Employee = require_permission("chess:coach")):
    lesson = await lms.get_lesson(db, lesson_id)
    if not lesson:
        raise HTTPException(404, "Không tìm thấy bài giảng")
    await _load_class_or_403(db, lesson.class_id, user, manage=True)
    await lms.delete_lesson(db, lesson)
    await db.commit()
    return {"deleted": True}


# ── Assignments ──

def _assignment_dto(a: ChessAssignment) -> dict:
    return {
        "id": str(a.id), "class_id": str(a.class_id), "title": a.title,
        "description": a.description, "kind": a.kind,
        "puzzle_ids": [str(p) for p in (a.puzzle_ids or [])],
        "study_set_id": str(a.study_set_id) if a.study_set_id else None,
        "lesson_id": str(a.lesson_id) if a.lesson_id else None,
        "due_at": a.due_at.isoformat() if a.due_at else None,
        "created_at": a.created_at.isoformat(),
    }


@router.get("/chess/classes/{class_id}/assignments")
async def list_assignments(class_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: Employee = require_permission("chess:read")):
    cls = await _load_class_or_403(db, class_id, user)
    assignments = await lms.list_assignments(db, class_id)
    role = lms.class_role(user, cls)
    items = []
    for a in assignments:
        dto = _assignment_dto(a)
        # students see their own progress
        if role == "student":
            dto["progress"] = await lms.assignment_progress(db, a, user.id)
        items.append(dto)
    return {"items": items}


@router.post("/chess/classes/{class_id}/assignments")
async def create_assignment(class_id: uuid.UUID, body: AssignmentBody, db: AsyncSession = Depends(get_db), user: Employee = require_permission("chess:coach")):
    cls = await _load_class_or_403(db, class_id, user, manage=True)
    a = await lms.create_assignment(
        db, user, cls, title=body.title, description=body.description, kind=body.kind,
        puzzle_ids=body.puzzle_ids, study_set_id=body.study_set_id, lesson_id=body.lesson_id, due_at=body.due_at,
    )
    await log_audit(db, user, "create", "chess_assignment", str(a.id))
    await db.commit()
    return _assignment_dto(a)


@router.get("/chess/assignments/{assignment_id}/progress")
async def assignment_progress(assignment_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: Employee = require_permission("chess:read")):
    a = await lms.get_assignment(db, assignment_id)
    if not a:
        raise HTTPException(404, "Không tìm thấy bài giao")
    cls = await _load_class_or_403(db, a.class_id, user)
    role = lms.class_role(user, cls)
    if role in ("coach", "admin"):
        return {"rows": await lms.class_progress(db, a, cls)}
    return {"rows": [{"employee_id": str(user.id), "name": user.name, **(await lms.assignment_progress(db, a, user.id))}]}


@router.delete("/chess/assignments/{assignment_id}")
async def delete_assignment(assignment_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: Employee = require_permission("chess:coach")):
    a = await lms.get_assignment(db, assignment_id)
    if not a:
        raise HTTPException(404, "Không tìm thấy bài giao")
    await _load_class_or_403(db, a.class_id, user, manage=True)
    await lms.delete_assignment(db, a)
    await db.commit()
    return {"deleted": True}
