"""Chess LMS service — classes, roster, lessons, assignments, progress.

Access is membership-based: a class is visible to its members (coach/students)
and admins. Coaches manage; students view their classes + assignments. Puzzle
assignment progress is computed from ChessPuzzleAttempt (no separate table).
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import delete as sql_delete
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import (
    ChessAssignment,
    ChessClass,
    ChessClassMember,
    ChessLesson,
    ChessPuzzleAttempt,
    Employee,
)


# ── Classes & roster ──

async def create_class(session: AsyncSession, user: Employee, *, name: str, description: Optional[str] = None) -> ChessClass:
    cls = ChessClass(name=name.strip(), description=description, coach_employee_id=user.id, scope_type="global")
    session.add(cls)
    await session.flush()
    session.add(ChessClassMember(class_id=cls.id, employee_id=user.id, role="coach"))
    await session.flush()
    return cls


async def list_classes_for_user(session: AsyncSession, user: Employee) -> list[ChessClass]:
    if user.role == "admin":
        stmt = select(ChessClass).order_by(ChessClass.created_at.desc())
    else:
        stmt = (
            select(ChessClass)
            .join(ChessClassMember, ChessClassMember.class_id == ChessClass.id)
            .where(ChessClassMember.employee_id == user.id)
            .order_by(ChessClass.created_at.desc())
        )
    return list((await session.execute(stmt)).scalars().all())


async def get_class(session: AsyncSession, class_id: uuid.UUID) -> Optional[ChessClass]:
    return (await session.execute(
        select(ChessClass)
        .options(selectinload(ChessClass.members).selectinload(ChessClassMember.employee))
        .where(ChessClass.id == class_id)
    )).scalar_one_or_none()


def class_role(user: Employee, cls: ChessClass) -> Optional[str]:
    """Return 'admin' | 'coach' | 'student' | None for the user in this class.
    Requires cls.members loaded."""
    if user.role == "admin":
        return "admin"
    for m in cls.members:
        if m.employee_id == user.id:
            return m.role
    return None


def can_manage_class(user: Employee, cls: ChessClass) -> bool:
    return class_role(user, cls) in ("admin", "coach")


async def add_member(session: AsyncSession, cls: ChessClass, employee_id: uuid.UUID, role: str = "student") -> ChessClassMember:
    existing = next((m for m in cls.members if m.employee_id == employee_id), None)
    if existing:
        existing.role = role
        await session.flush()
        return existing
    m = ChessClassMember(class_id=cls.id, employee_id=employee_id, role=role)
    session.add(m)
    await session.flush()
    return m


async def remove_member(session: AsyncSession, class_id: uuid.UUID, employee_id: uuid.UUID) -> None:
    await session.execute(sql_delete(ChessClassMember).where(
        ChessClassMember.class_id == class_id, ChessClassMember.employee_id == employee_id,
    ))


async def delete_class(session: AsyncSession, cls: ChessClass) -> None:
    await session.delete(cls)


# ── Lessons ──

async def create_lesson(session: AsyncSession, user: Employee, cls: ChessClass, *, title: str, content_md: str = "", study_set_id: Optional[uuid.UUID] = None) -> ChessLesson:
    next_pos = (await session.execute(
        select(func.coalesce(func.max(ChessLesson.position), -1)).where(ChessLesson.class_id == cls.id)
    )).scalar_one() + 1
    lesson = ChessLesson(
        class_id=cls.id, title=title.strip(), content_md=content_md,
        study_set_id=study_set_id, position=next_pos, created_by_employee_id=user.id,
    )
    session.add(lesson)
    await session.flush()
    return lesson


async def list_lessons(session: AsyncSession, class_id: uuid.UUID) -> list[ChessLesson]:
    return list((await session.execute(
        select(ChessLesson).where(ChessLesson.class_id == class_id).order_by(ChessLesson.position)
    )).scalars().all())


async def get_lesson(session: AsyncSession, lesson_id: uuid.UUID) -> Optional[ChessLesson]:
    return (await session.execute(
        select(ChessLesson).where(ChessLesson.id == lesson_id)
    )).scalar_one_or_none()


async def delete_lesson(session: AsyncSession, lesson: ChessLesson) -> None:
    await session.delete(lesson)


# ── Assignments ──

async def create_assignment(
    session: AsyncSession, user: Employee, cls: ChessClass, *,
    title: str, description: Optional[str] = None, kind: str = "puzzles",
    puzzle_ids: Optional[list[uuid.UUID]] = None, study_set_id: Optional[uuid.UUID] = None,
    lesson_id: Optional[uuid.UUID] = None, due_at: Optional[datetime] = None,
) -> ChessAssignment:
    a = ChessAssignment(
        class_id=cls.id, title=title.strip(), description=description, kind=kind,
        puzzle_ids=puzzle_ids or [], study_set_id=study_set_id, lesson_id=lesson_id,
        due_at=due_at, created_by_employee_id=user.id,
    )
    session.add(a)
    await session.flush()
    return a


async def list_assignments(session: AsyncSession, class_id: uuid.UUID) -> list[ChessAssignment]:
    return list((await session.execute(
        select(ChessAssignment).where(ChessAssignment.class_id == class_id).order_by(ChessAssignment.created_at.desc())
    )).scalars().all())


async def get_assignment(session: AsyncSession, assignment_id: uuid.UUID) -> Optional[ChessAssignment]:
    return (await session.execute(
        select(ChessAssignment).where(ChessAssignment.id == assignment_id)
    )).scalar_one_or_none()


async def delete_assignment(session: AsyncSession, a: ChessAssignment) -> None:
    await session.delete(a)


async def assignment_progress(session: AsyncSession, a: ChessAssignment, employee_id: uuid.UUID) -> dict:
    """A student's progress on an assignment (puzzle assignments: solved/total)."""
    if a.kind == "puzzles":
        total = len(a.puzzle_ids or [])
        if total == 0:
            return {"solved": 0, "total": 0, "completed": True}
        solved = (await session.execute(
            select(func.count(distinct(ChessPuzzleAttempt.puzzle_id))).where(
                ChessPuzzleAttempt.employee_id == employee_id,
                ChessPuzzleAttempt.solved.is_(True),
                ChessPuzzleAttempt.puzzle_id.in_(a.puzzle_ids),
            )
        )).scalar() or 0
        return {"solved": solved, "total": total, "completed": solved >= total}
    # study/lesson assignments — no auto-tracking in the MVP.
    return {"solved": 0, "total": 0, "completed": False}


async def class_progress(session: AsyncSession, a: ChessAssignment, cls: ChessClass) -> list[dict]:
    """Per-student progress for the coach dashboard. Requires cls.members loaded."""
    out = []
    for m in cls.members:
        if m.role != "student":
            continue
        prog = await assignment_progress(session, a, m.employee_id)
        out.append({
            "employee_id": str(m.employee_id),
            "name": m.employee.name if m.employee else "?",
            **prog,
        })
    return out
