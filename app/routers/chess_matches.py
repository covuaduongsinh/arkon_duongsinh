"""Chess sparring matches router — create, poll, move, resign.

Polling-first realtime: clients GET /matches/{id} to read the authoritative
state. Requires chess:play. State + move legality live in chess_match_service.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import ChessMatch, Employee
from app.services import chess_match_service, chess_realtime
from app.services.audit_service import log_audit
from app.services.auth_service import require_permission

router = APIRouter()


class MatchResponse(BaseModel):
    id: uuid.UUID
    white_employee_id: Optional[uuid.UUID] = None
    black_employee_id: Optional[uuid.UUID] = None
    mode: str
    engine_level: Optional[int] = None
    status: str
    current_fen: str
    moves: list = []
    result: Optional[str] = None
    winner_employee_id: Optional[uuid.UUID] = None
    game_id: Optional[uuid.UUID] = None
    your_color: Optional[str] = None
    created_at: str
    updated_at: str


def _to_response(match: ChessMatch, user: Employee) -> MatchResponse:
    your_color = (
        "white" if match.white_employee_id == user.id
        else "black" if match.black_employee_id == user.id
        else None
    )
    return MatchResponse(
        id=match.id,
        white_employee_id=match.white_employee_id,
        black_employee_id=match.black_employee_id,
        mode=match.mode,
        engine_level=match.engine_level,
        status=match.status,
        current_fen=match.current_fen,
        moves=list(match.moves or []),
        result=match.result,
        winner_employee_id=match.winner_employee_id,
        game_id=match.game_id,
        your_color=your_color,
        created_at=match.created_at.isoformat(),
        updated_at=match.updated_at.isoformat(),
    )


class CreateMatchBody(BaseModel):
    mode: str = "human_vs_engine"
    player_color: str = "white"
    engine_level: int = 4


class MoveBody(BaseModel):
    uci: str


@router.get("/chess/matches")
async def list_matches(
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:play"),
):
    matches = await chess_match_service.list_matches(db, user)
    return {"items": [_to_response(m, user) for m in matches]}


@router.get("/chess/matches/open")
async def list_open_matches(
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:play"),
):
    """Joinable open human-vs-human challenges."""
    matches = await chess_match_service.list_open_matches(db, user)
    return {"items": [_to_response(m, user) for m in matches]}


@router.post("/chess/matches")
async def create_match(
    body: CreateMatchBody,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:play"),
):
    try:
        match = await chess_match_service.create_match(
            db, user,
            mode=body.mode, player_color=body.player_color,
            engine_level=body.engine_level,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    await log_audit(db, user, "create", "chess_match", str(match.id))
    # Commit now (not via get_db's post-response commit) so the match is durable
    # before the client navigates to it and fetches by id.
    await db.commit()
    return _to_response(match, user)


@router.get("/chess/matches/{match_id}")
async def get_match(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:play"),
):
    match = await chess_match_service.get_match(db, match_id)
    if not match:
        raise HTTPException(404, "Match not found")
    if not chess_match_service.can_access_match(user, match):
        raise HTTPException(403, "Access denied")
    return _to_response(match, user)


@router.post("/chess/matches/{match_id}/move")
async def move(
    match_id: uuid.UUID,
    body: MoveBody,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:play"),
):
    match = await chess_match_service.get_match(db, match_id)
    if not match:
        raise HTTPException(404, "Match not found")
    if not chess_match_service.can_access_match(user, match):
        raise HTTPException(403, "Access denied")
    try:
        match = await chess_match_service.apply_move(db, match, user, body.uci)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await db.commit()
    # Reload server-side onupdate columns (updated_at) within the async context;
    # otherwise serializing them in _to_response triggers a sync lazy-load.
    await db.refresh(match)
    await chess_realtime.publish_match(str(match.id), chess_match_service.serialize_match(match))
    return _to_response(match, user)


@router.post("/chess/matches/{match_id}/resign")
async def resign(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:play"),
):
    match = await chess_match_service.get_match(db, match_id)
    if not match:
        raise HTTPException(404, "Match not found")
    if not chess_match_service.can_access_match(user, match):
        raise HTTPException(403, "Access denied")
    try:
        match = await chess_match_service.resign(db, match, user)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await log_audit(db, user, "update", "chess_match", str(match_id), reason="resign")
    await db.commit()
    await db.refresh(match)
    await chess_realtime.publish_match(str(match.id), chess_match_service.serialize_match(match))
    return _to_response(match, user)


@router.post("/chess/matches/{match_id}/join")
async def join_match(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:play"),
):
    """Join an open human-vs-human challenge (claim the empty seat)."""
    match = await chess_match_service.get_match(db, match_id)
    if not match:
        raise HTTPException(404, "Match not found")
    try:
        match = await chess_match_service.join_match(db, match, user)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await db.commit()
    await db.refresh(match)
    await chess_realtime.publish_match(str(match.id), chess_match_service.serialize_match(match))
    return _to_response(match, user)
