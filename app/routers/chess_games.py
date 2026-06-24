"""Chess games router — list, import (PGN file or text), view, delete.

Scope filtering reuses permission_engine via chess_service. Mutations require
chess:create / chess:delete and are audit-logged.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import ChessGame, Employee
from app.services import chess_service
from app.services.audit_service import log_audit
from app.services.auth_service import require_permission
from app.services.permission_engine import can_access_chess

router = APIRouter()


class ChessGameSummary(BaseModel):
    id: uuid.UUID
    slug: Optional[str] = None
    white: Optional[str] = None
    black: Optional[str] = None
    result: Optional[str] = None
    eco: Optional[str] = None
    opening_name: Optional[str] = None
    white_elo: Optional[int] = None
    black_elo: Optional[int] = None
    event: Optional[str] = None
    played_at: Optional[str] = None
    ply_count: int = 0
    source_game: str = "import"
    scope_type: str = "global"
    scope_id: Optional[uuid.UUID] = None
    created_at: str

    model_config = {"from_attributes": True}


class ChessGameDetail(ChessGameSummary):
    pgn: str
    headers: dict = {}
    final_fen: Optional[str] = None
    knowledge_type_slugs: list[str] = []
    analysis_status: str = "none"
    analysis_json: Optional[dict] = None


def _summary(g: ChessGame) -> ChessGameSummary:
    return ChessGameSummary(
        id=g.id, slug=g.slug, white=g.white, black=g.black, result=g.result, eco=g.eco,
        opening_name=g.opening_name, white_elo=g.white_elo, black_elo=g.black_elo,
        event=g.event, played_at=g.played_at, ply_count=g.ply_count,
        source_game=g.source_game, scope_type=g.scope_type, scope_id=g.scope_id,
        created_at=g.created_at.isoformat(),
    )


@router.get("/chess/games")
async def list_games(
    search: Optional[str] = Query(None),
    eco: Optional[str] = Query(None),
    result: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:read"),
):
    games, total = await chess_service.list_games(
        db, user, search=search, eco=eco, result=result, page=page, page_size=page_size,
    )
    return {
        "items": [_summary(g) for g in games],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, -(-total // page_size)),
    }


@router.post("/chess/games/import")
async def import_games(
    file: Optional[UploadFile] = File(None),
    pgn: Optional[str] = Form(None),
    scope_type: str = Form("global"),
    scope_id: Optional[uuid.UUID] = Form(None),
    knowledge_type_slugs: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:create"),
):
    """Import one or more games from an uploaded .pgn file or pasted PGN text."""
    text = pgn
    if file is not None:
        raw = await file.read()
        try:
            text = raw.decode("utf-8", errors="replace")
        except Exception as e:
            raise HTTPException(400, f"Could not read PGN file: {e}")
    if not text or not text.strip():
        raise HTTPException(400, "Provide a PGN file or PGN text")

    slugs = [s.strip() for s in knowledge_type_slugs.split(",")] if knowledge_type_slugs else []
    slugs = [s for s in slugs if s]

    try:
        created = await chess_service.import_pgn(
            db, user, text,
            scope_type=scope_type, scope_id=scope_id, knowledge_type_slugs=slugs,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    for g in created:
        await log_audit(db, user, "create", "chess_game", str(g.id))

    await db.commit()
    return {"imported": len(created), "items": [_summary(g) for g in created]}


@router.get("/chess/games/{game_id}")
async def get_game(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:read"),
):
    game = await chess_service.get_game(db, game_id)
    if not game:
        raise HTTPException(404, "Game not found")
    if not can_access_chess(user, game, "read"):
        raise HTTPException(403, "Access denied")
    return ChessGameDetail(
        **_summary(game).model_dump(),
        pgn=game.pgn, headers=game.headers or {},
        final_fen=game.final_fen, knowledge_type_slugs=game.knowledge_type_slugs or [],
        analysis_status=game.analysis_status, analysis_json=game.analysis_json,
    )


@router.post("/chess/games/{game_id}/analyze")
async def analyze_game(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:read"),
):
    """Enqueue async whole-game engine analysis. Poll GET /chess/games/{id} for
    analysis_status -> "done" and the analysis_json report."""
    game = await chess_service.get_game(db, game_id)
    if not game:
        raise HTTPException(404, "Game not found")
    if not can_access_chess(user, game, "read"):
        raise HTTPException(403, "Access denied")
    if game.analysis_status in ("queued", "running"):
        return {"status": game.analysis_status}

    game.analysis_status = "queued"
    await db.commit()

    from app.worker import get_arq_pool
    pool = await get_arq_pool()
    await pool.enqueue_job("analyze_game_task", str(game.id))
    return {"status": "queued"}


@router.post("/chess/games/{game_id}/to-source")
async def game_to_source(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:create"),
):
    """Send a game into the wiki/MRP pipeline as a 'chess' knowledge Source."""
    game = await chess_service.get_game(db, game_id)
    if not game:
        raise HTTPException(404, "Game not found")
    if not can_access_chess(user, game, "read"):
        raise HTTPException(403, "Access denied")

    source = await chess_service.game_to_source(db, user, game)
    await log_audit(db, user, "create", "source", str(source.id), reason="chess game → source")
    await db.commit()

    # Enqueue the same MRP pipeline used by document ingestion.
    from app.worker import get_arq_pool
    pool = await get_arq_pool()
    job = await pool.enqueue_job("ingest_map_reduce_task", str(source.id))
    if job:
        source.job_id = job.job_id
        await db.commit()

    return {"source_id": source.id, "status": "queued", "job_id": source.job_id}


@router.delete("/chess/games/{game_id}")
async def delete_game(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:delete"),
):
    game = await chess_service.get_game(db, game_id)
    if not game:
        raise HTTPException(404, "Game not found")
    if not can_access_chess(user, game, "delete"):
        raise HTTPException(403, "Access denied")
    await chess_service.delete_game(db, game)
    await log_audit(db, user, "delete", "chess_game", str(game_id))
    await db.commit()
    return {"deleted": True}
