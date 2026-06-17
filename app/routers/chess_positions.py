"""Chess positions router — FEN store CRUD + FEN validation."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import ChessPosition, Employee
from app.services import chess_service
from app.services.audit_service import log_audit
from app.services.auth_service import require_permission
from app.services.permission_engine import can_access_chess

router = APIRouter()


class PositionResponse(BaseModel):
    id: uuid.UUID
    fen: str
    label: Optional[str] = None
    description: Optional[str] = None
    eval_cp: Optional[int] = None
    best_move: Optional[str] = None
    eval_depth: Optional[int] = None
    themes: list[str] = []
    scope_type: str = "global"
    scope_id: Optional[uuid.UUID] = None
    created_at: str

    model_config = {"from_attributes": True}


def _response(p: ChessPosition) -> PositionResponse:
    return PositionResponse(
        id=p.id, fen=p.fen, label=p.label, description=p.description,
        eval_cp=p.eval_cp, best_move=p.best_move, eval_depth=p.eval_depth,
        themes=p.themes or [], scope_type=p.scope_type, scope_id=p.scope_id,
        created_at=p.created_at.isoformat(),
    )


class CreatePositionBody(BaseModel):
    fen: str
    label: Optional[str] = None
    description: Optional[str] = None
    themes: list[str] = []
    scope_type: str = "global"
    scope_id: Optional[uuid.UUID] = None


class ValidateFenBody(BaseModel):
    fen: str


@router.get("/chess/positions")
async def list_positions(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:read"),
):
    positions, total = await chess_service.list_positions(db, user, page=page, page_size=page_size)
    return {
        "items": [_response(p) for p in positions],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, -(-total // page_size)),
    }


@router.post("/chess/positions/validate")
async def validate_position(
    body: ValidateFenBody,
    user: Employee = require_permission("chess:read"),
):
    try:
        normalized = chess_service.validate_fen(body.fen)
    except ValueError as e:
        return {"valid": False, "error": str(e)}
    return {"valid": True, "fen": normalized}


@router.post("/chess/positions")
async def create_position(
    body: CreatePositionBody,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:create"),
):
    try:
        pos = await chess_service.create_position(
            db, user,
            fen=body.fen, label=body.label, description=body.description,
            themes=body.themes, scope_type=body.scope_type, scope_id=body.scope_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    await log_audit(db, user, "create", "chess_position", str(pos.id))
    await db.commit()
    return _response(pos)


@router.get("/chess/positions/{position_id}")
async def get_position(
    position_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:read"),
):
    pos = await chess_service.get_position(db, position_id)
    if not pos:
        raise HTTPException(404, "Position not found")
    if not can_access_chess(user, pos, "read"):
        raise HTTPException(403, "Access denied")
    return _response(pos)


@router.delete("/chess/positions/{position_id}")
async def delete_position(
    position_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:delete"),
):
    pos = await chess_service.get_position(db, position_id)
    if not pos:
        raise HTTPException(404, "Position not found")
    if not can_access_chess(user, pos, "delete"):
        raise HTTPException(403, "Access denied")
    await chess_service.delete_position(db, pos)
    await log_audit(db, user, "delete", "chess_position", str(position_id))
    await db.commit()
    return {"deleted": True}
