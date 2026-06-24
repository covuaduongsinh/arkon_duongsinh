"""Chess puzzles router — browse, fetch next, create, solve-attempt, stats.

Solutions are withheld from non-coaches on read; attempts are validated
server-side and the solution is revealed in the attempt response. Solving/
playing requires chess:play; creating requires chess:create; publishing a
puzzle requires chess:coach.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import ChessPuzzle, Employee
from app.services import chess_service
from app.services.audit_service import log_audit
from app.services.auth_service import require_permission
from app.services.permission_engine import _get_user_permissions, can_access_chess

router = APIRouter()


def _can_coach(user: Employee) -> bool:
    return user.role == "admin" or "chess:coach" in _get_user_permissions(user)


class PuzzlePublic(BaseModel):
    """Puzzle without the solution — what solvers see."""
    id: uuid.UUID
    slug: Optional[str] = None
    fen: str
    side_to_move: str
    themes: list[str] = []
    rating: Optional[int] = None
    popularity: Optional[int] = None
    nb_plays: Optional[int] = None
    piece_count: Optional[int] = None
    opening_name: Optional[str] = None
    source: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    is_published: bool = False
    scope_type: str = "global"
    scope_id: Optional[uuid.UUID] = None
    created_at: str

    model_config = {"from_attributes": True}


class PuzzleWithSolution(PuzzlePublic):
    solution_moves: list[str] = []


def _public(p: ChessPuzzle) -> PuzzlePublic:
    return PuzzlePublic(
        id=p.id, slug=p.slug, fen=p.fen, side_to_move=p.side_to_move, themes=p.themes or [],
        rating=p.rating, popularity=p.popularity, nb_plays=p.nb_plays,
        piece_count=p.piece_count, opening_name=p.opening_name, source=p.source,
        title=p.title, description=p.description,
        is_published=p.is_published, scope_type=p.scope_type, scope_id=p.scope_id,
        created_at=p.created_at.isoformat(),
    )


class CreatePuzzleBody(BaseModel):
    fen: str
    solution_moves: list[str]
    themes: list[str] = []
    rating: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    is_published: bool = False
    scope_type: str = "global"
    scope_id: Optional[uuid.UUID] = None


class UpdatePuzzleBody(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    themes: Optional[list[str]] = None
    rating: Optional[int] = None
    opening_name: Optional[str] = None
    is_published: Optional[bool] = None


class AttemptBody(BaseModel):
    moves_played: list[str]
    time_ms: Optional[int] = None
    hints_used: int = 0


class StepBody(BaseModel):
    moves: list[str]  # all moves played so far (solver + replies), solver's last
    time_ms: Optional[int] = None


@router.get("/chess/puzzles")
async def list_puzzles(
    theme: Optional[str] = Query(None),
    themes: Optional[list[str]] = Query(None),
    search: Optional[str] = Query(None),
    opening: Optional[str] = Query(None),
    side: Optional[str] = Query(None),
    min_rating: Optional[int] = Query(None),
    max_rating: Optional[int] = Query(None),
    min_pieces: Optional[int] = Query(None),
    max_pieces: Optional[int] = Query(None),
    source: Optional[str] = Query(None),
    sort: str = Query("recent"),
    include_drafts: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:read"),
):
    puzzles, total = await chess_service.list_puzzles(
        db, user, theme=theme, themes=themes, search=search, opening=opening, side=side,
        min_rating=min_rating, max_rating=max_rating,
        min_pieces=min_pieces, max_pieces=max_pieces, source=source, sort=sort,
        published_only=not (include_drafts and _can_coach(user)),
        page=page, page_size=page_size,
    )
    return {
        "items": [_public(p) for p in puzzles],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, -(-total // page_size)),
    }


@router.get("/chess/puzzles/facets")
async def puzzle_facets(
    include_drafts: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:read"),
):
    return await chess_service.puzzle_facets(
        db, user, published_only=not (include_drafts and _can_coach(user)),
    )


@router.get("/chess/puzzles/next")
async def next_puzzle(
    theme: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:read"),
):
    puzzle = await chess_service.get_next_puzzle(db, user, theme=theme)
    if not puzzle:
        return {"puzzle": None}
    return {"puzzle": _public(puzzle)}


@router.get("/chess/puzzles/stats/me")
async def my_stats(
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:read"),
):
    return await chess_service.puzzle_stats(db, user)


@router.post("/chess/puzzles")
async def create_puzzle(
    body: CreatePuzzleBody,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:create"),
):
    if body.is_published and not _can_coach(user):
        raise HTTPException(403, "Publishing puzzles requires chess:coach")
    try:
        puzzle = await chess_service.create_puzzle(
            db, user,
            fen=body.fen, solution_moves=body.solution_moves, themes=body.themes,
            rating=body.rating, title=body.title, description=body.description,
            is_published=body.is_published,
            scope_type=body.scope_type, scope_id=body.scope_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    await log_audit(db, user, "create", "chess_puzzle", str(puzzle.id))
    await db.commit()
    return PuzzleWithSolution(**_public(puzzle).model_dump(), solution_moves=puzzle.solution_moves)


@router.get("/chess/puzzles/{puzzle_id}")
async def get_puzzle(
    puzzle_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:read"),
):
    puzzle = await chess_service.get_puzzle(db, puzzle_id)
    if not puzzle:
        raise HTTPException(404, "Puzzle not found")
    if not can_access_chess(user, puzzle, "read"):
        raise HTTPException(403, "Access denied")
    # Drafts are visible to coaches only — hide their existence from solvers.
    if not puzzle.is_published and not _can_coach(user):
        raise HTTPException(404, "Puzzle not found")
    # Coaches see the solution; solvers don't.
    if _can_coach(user):
        return PuzzleWithSolution(**_public(puzzle).model_dump(), solution_moves=puzzle.solution_moves)
    return _public(puzzle)


@router.patch("/chess/puzzles/{puzzle_id}")
async def update_puzzle(
    puzzle_id: uuid.UUID,
    body: UpdatePuzzleBody,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:edit"),
):
    puzzle = await chess_service.get_puzzle(db, puzzle_id)
    if not puzzle:
        raise HTTPException(404, "Puzzle not found")
    if not can_access_chess(user, puzzle, "edit"):
        raise HTTPException(403, "Access denied")
    # Publishing/unpublishing is a coach action (mirrors create gating).
    if body.is_published is not None and body.is_published != puzzle.is_published and not _can_coach(user):
        raise HTTPException(403, "Publishing puzzles requires chess:coach")
    puzzle = await chess_service.update_puzzle(
        db, puzzle,
        title=body.title, description=body.description, themes=body.themes,
        rating=body.rating, opening_name=body.opening_name, is_published=body.is_published,
    )
    await log_audit(db, user, "update", "chess_puzzle", str(puzzle.id))
    await db.commit()
    return PuzzleWithSolution(**_public(puzzle).model_dump(), solution_moves=puzzle.solution_moves)


@router.delete("/chess/puzzles/{puzzle_id}")
async def delete_puzzle(
    puzzle_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:delete"),
):
    puzzle = await chess_service.get_puzzle(db, puzzle_id)
    if not puzzle:
        raise HTTPException(404, "Puzzle not found")
    if not can_access_chess(user, puzzle, "delete"):
        raise HTTPException(403, "Access denied")
    await chess_service.delete_puzzle(db, puzzle)
    await log_audit(db, user, "delete", "chess_puzzle", str(puzzle_id))
    await db.commit()
    return {"deleted": True}


@router.post("/chess/puzzles/{puzzle_id}/step")
async def step_puzzle(
    puzzle_id: uuid.UUID,
    body: StepBody,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:play"),
):
    """Validate one step of a multi-move puzzle and return the opponent's reply.

    The solution stays hidden — only the next reply is revealed. A terminal
    state (wrong move or solved) is recorded as a ChessPuzzleAttempt for stats.
    """
    puzzle = await chess_service.get_puzzle(db, puzzle_id)
    if not puzzle:
        raise HTTPException(404, "Puzzle not found")
    if not can_access_chess(user, puzzle, "read"):
        raise HTTPException(403, "Access denied")
    if not puzzle.is_published and not _can_coach(user):
        raise HTTPException(404, "Puzzle not found")

    result = chess_service.check_puzzle_step(puzzle.solution_moves, body.moves)
    if (not result["correct"]) or result["solved"]:
        await chess_service.record_attempt(
            db, user, puzzle, moves_played=body.moves, time_ms=body.time_ms,
        )
        await db.commit()
        # Reveal the full solution only once the puzzle is over.
        result["solution_moves"] = list(puzzle.solution_moves)
    return result


@router.post("/chess/puzzles/{puzzle_id}/attempt")
async def attempt_puzzle(
    puzzle_id: uuid.UUID,
    body: AttemptBody,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:play"),
):
    puzzle = await chess_service.get_puzzle(db, puzzle_id)
    if not puzzle:
        raise HTTPException(404, "Puzzle not found")
    if not can_access_chess(user, puzzle, "read"):
        raise HTTPException(403, "Access denied")
    if not puzzle.is_published and not _can_coach(user):
        raise HTTPException(404, "Puzzle not found")
    attempt = await chess_service.record_attempt(
        db, user, puzzle,
        moves_played=body.moves_played, time_ms=body.time_ms, hints_used=body.hints_used,
    )
    await db.commit()
    # Reveal the solution after the attempt so the UI can show the right line.
    return {
        "solved": attempt.solved,
        "solution_moves": puzzle.solution_moves,
        "attempt_id": attempt.id,
    }
