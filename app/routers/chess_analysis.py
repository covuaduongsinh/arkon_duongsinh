"""Chess analysis router — server-side Stockfish evaluation of a FEN.

Bounded synchronous analysis (depth-capped + wall clock) backed by
chess_engine_service. Primarily for callers without an in-browser engine
(the portal uses the WASM engine client-side). Optionally caches the eval onto
a saved ChessPosition when `position_id` is supplied.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Employee
from app.services import chess_engine_service, chess_service
from app.services.auth_service import require_permission
from app.services.permission_engine import can_access_chess

router = APIRouter()


class AnalyzeBody(BaseModel):
    fen: str
    depth: int = 16
    # When set, cache the resulting eval onto this saved position.
    position_id: Optional[uuid.UUID] = None


@router.get("/chess/analysis/status")
async def analysis_status(
    user: Employee = require_permission("chess:read"),
):
    """Whether server-side engine analysis is available."""
    return {"engine_available": chess_engine_service.engine_available()}


@router.post("/chess/analysis")
async def analyze(
    body: AnalyzeBody,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:read"),
):
    try:
        fen = chess_service.validate_fen(body.fen)
    except ValueError as e:
        raise HTTPException(400, str(e))

    result = await chess_engine_service.analyze_fen(fen, depth=body.depth)
    if result is None:
        raise HTTPException(
            503,
            "Server-side chess engine is not available. Use the in-browser analysis board instead.",
        )

    # Optional: cache eval onto a saved position the user can access.
    if body.position_id is not None:
        pos = await chess_service.get_position(db, body.position_id)
        if pos and can_access_chess(user, pos, "edit"):
            pos.eval_cp = result["eval_cp"]
            pos.best_move = result["best_move"]
            pos.eval_depth = result["depth"]

    return result
