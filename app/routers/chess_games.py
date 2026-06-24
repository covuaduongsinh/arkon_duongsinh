"""Chess games router — list, import (PGN file or text), view, delete.

Scope filtering reuses permission_engine via chess_service. Mutations require
chess:create / chess:delete and are audit-logged.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import ChessGame, Employee
from app.services import chess_service
from app.services.audit_service import log_audit
from app.services.auth_service import require_permission
from app.services.permission_engine import _get_user_permissions, can_access_chess

router = APIRouter()


def _can_coach(user: Employee) -> bool:
    return user.role == "admin" or "chess:coach" in _get_user_permissions(user)


class ChessGameSummary(BaseModel):
    id: uuid.UUID
    slug: Optional[str] = None
    title: Optional[str] = None
    white: Optional[str] = None
    black: Optional[str] = None
    result: Optional[str] = None
    eco: Optional[str] = None
    opening_name: Optional[str] = None
    white_elo: Optional[int] = None
    black_elo: Optional[int] = None
    event: Optional[str] = None
    site: Optional[str] = None
    played_at: Optional[str] = None
    played_year: Optional[int] = None
    ply_count: int = 0
    final_fen: Optional[str] = None
    themes: list[str] = []
    source_game: str = "import"
    is_published: bool = False
    popularity: int = 0
    blunder_count: Optional[int] = None
    brilliant_count: Optional[int] = None
    analysis_status: str = "none"
    scope_type: str = "global"
    scope_id: Optional[uuid.UUID] = None
    created_at: str

    model_config = {"from_attributes": True}


class ChessGameDetail(ChessGameSummary):
    pgn: str
    description: Optional[str] = None
    headers: dict = {}
    knowledge_type_slugs: list[str] = []
    analysis_json: Optional[dict] = None


def _summary(g: ChessGame) -> ChessGameSummary:
    return ChessGameSummary(
        id=g.id, slug=g.slug, title=g.title, white=g.white, black=g.black, result=g.result, eco=g.eco,
        opening_name=g.opening_name, white_elo=g.white_elo, black_elo=g.black_elo,
        event=g.event, site=g.site, played_at=g.played_at, played_year=g.played_year,
        ply_count=g.ply_count, final_fen=g.final_fen, themes=g.themes or [], source_game=g.source_game,
        is_published=g.is_published, popularity=g.popularity,
        blunder_count=g.blunder_count, brilliant_count=g.brilliant_count,
        analysis_status=g.analysis_status, scope_type=g.scope_type, scope_id=g.scope_id,
        created_at=g.created_at.isoformat(),
    )


@router.get("/chess/games")
async def list_games(
    search: Optional[str] = Query(None),
    white: Optional[str] = Query(None),
    black: Optional[str] = Query(None),
    eco: Optional[str] = Query(None),
    result: Optional[str] = Query(None),
    opening: Optional[str] = Query(None),
    event: Optional[str] = Query(None),
    site: Optional[str] = Query(None),
    themes: Optional[list[str]] = Query(None),
    source_game: Optional[str] = Query(None),
    analysis_status: Optional[str] = Query(None),
    min_elo: Optional[int] = Query(None),
    max_elo: Optional[int] = Query(None),
    min_ply: Optional[int] = Query(None),
    max_ply: Optional[int] = Query(None),
    min_year: Optional[int] = Query(None),
    max_year: Optional[int] = Query(None),
    min_blunders: Optional[int] = Query(None),
    min_brilliants: Optional[int] = Query(None),
    named: bool = Query(False),
    sort: str = Query("recent"),
    include_drafts: bool = Query(False),
    drafts_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:read"),
):
    can_coach = _can_coach(user)
    show_drafts = (include_drafts or drafts_only) and can_coach
    games, total = await chess_service.list_games(
        db, user, search=search, white=white, black=black, eco=eco, result=result,
        opening=opening, event=event, site=site, themes=themes, source_game=source_game,
        analysis_status=analysis_status, min_elo=min_elo, max_elo=max_elo,
        min_ply=min_ply, max_ply=max_ply, min_year=min_year, max_year=max_year,
        min_blunders=min_blunders, min_brilliants=min_brilliants, named=named, sort=sort,
        published_only=not show_drafts, drafts_only=(drafts_only and can_coach),
        page=page, page_size=page_size,
    )
    return {
        "items": [_summary(g) for g in games],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, -(-total // page_size)),
    }


@router.get("/chess/games/facets")
async def game_facets(
    include_drafts: bool = Query(False),
    drafts_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:read"),
):
    can_coach = _can_coach(user)
    show_drafts = (include_drafts or drafts_only) and can_coach
    return await chess_service.game_facets(
        db, user, published_only=not show_drafts, drafts_only=(drafts_only and can_coach),
    )


class UpdateGameBody(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    themes: Optional[list[str]] = None
    opening_name: Optional[str] = None
    is_published: Optional[bool] = None


class BulkPublishBody(BaseModel):
    ids: list[uuid.UUID]
    publish: bool = True


@router.post("/chess/games/bulk-publish")
async def bulk_publish_games(
    body: BulkPublishBody,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:coach"),
):
    """Publish/unpublish many games at once (coach). Declared before the dynamic
    "/chess/games/{game_id}" route so the literal path wins."""
    if not body.ids:
        return {"updated": 0, "skipped": 0}
    if len(body.ids) > 500:
        raise HTTPException(400, "Tối đa 500 ván mỗi lần")
    games = (await db.execute(select(ChessGame).where(ChessGame.id.in_(body.ids)))).scalars().all()
    updated = skipped = 0
    for g in games:
        if not can_access_chess(user, g, "edit"):
            skipped += 1
            continue
        if g.is_published != body.publish:
            g.is_published = body.publish
            await log_audit(db, user, "publish" if body.publish else "unpublish", "chess_game", str(g.id))
            updated += 1
    await db.commit()
    return {"updated": updated, "skipped": skipped}


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
    # Drafts are coach-only; hide their existence from students.
    if not game.is_published and not _can_coach(user):
        raise HTTPException(404, "Game not found")
    return ChessGameDetail(
        **_summary(game).model_dump(),
        pgn=game.pgn, description=game.description, headers=game.headers or {},
        knowledge_type_slugs=game.knowledge_type_slugs or [],
        analysis_json=game.analysis_json,
    )


@router.post("/chess/games/{game_id}/view")
async def register_view(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:read"),
):
    """Bump the view count ("popularity"). Called once per open by the detail page —
    kept off GET so the analysis-status poll doesn't inflate it."""
    game = await chess_service.get_game(db, game_id)
    if not game:
        raise HTTPException(404, "Game not found")
    if not can_access_chess(user, game, "read"):
        raise HTTPException(403, "Access denied")
    if not game.is_published and not _can_coach(user):
        raise HTTPException(404, "Game not found")
    game.popularity = (game.popularity or 0) + 1
    await db.commit()
    return {"popularity": game.popularity}


@router.patch("/chess/games/{game_id}")
async def update_game(
    game_id: uuid.UUID,
    body: UpdateGameBody,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:edit"),
):
    game = await chess_service.get_game(db, game_id)
    if not game:
        raise HTTPException(404, "Game not found")
    if not can_access_chess(user, game, "edit"):
        raise HTTPException(403, "Access denied")
    # Publishing/unpublishing is a coach action (mirrors puzzle gating).
    if body.is_published is not None and body.is_published != game.is_published and not _can_coach(user):
        raise HTTPException(403, "Publishing games requires chess:coach")
    game = await chess_service.update_game(
        db, game, title=body.title, description=body.description, themes=body.themes,
        opening_name=body.opening_name, is_published=body.is_published,
    )
    await log_audit(db, user, "update", "chess_game", str(game.id))
    detail = ChessGameDetail(
        **_summary(game).model_dump(), pgn=game.pgn, description=game.description,
        headers=game.headers or {}, final_fen=game.final_fen,
        knowledge_type_slugs=game.knowledge_type_slugs or [], analysis_json=game.analysis_json,
    )
    await db.commit()
    return detail


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
