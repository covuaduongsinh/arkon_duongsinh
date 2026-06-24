"""Chess wikilink router — resolve / search / backlinks for chess entities.

Powers the `[[game:…]]` / `![[position:…]]` wikilink feature:
  * GET  /chess/link-targets — autocomplete pool when typing `[[`
  * POST /chess/resolve-links — batch resolve tokens → chip/embed metadata
  * GET  /chess/backlinks     — wiki pages & lessons referencing an entity

All endpoints require chess:read and reuse chess_service's scope-aware helpers.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Employee
from app.services import chess_service
from app.services.auth_service import require_permission

router = APIRouter()


class ResolveLinksBody(BaseModel):
    tokens: list[str] = []


@router.get("/chess/link-targets")
async def link_targets(
    q: Optional[str] = Query(None, description="Substring to match slug/title/players"),
    type: Optional[str] = Query(None, description="Restrict to one namespace: game|position|puzzle|study"),
    limit: int = Query(8, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:read"),
):
    """Chess entities for the `[[` autocomplete pool (scope-filtered)."""
    items = await chess_service.search_link_targets(db, user, q=q, type_filter=type, limit=limit)
    return {"items": items}


@router.post("/chess/resolve-links")
async def resolve_links(
    body: ResolveLinksBody,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:read"),
):
    """Batch-resolve `[[ns:ident]]` tokens to metadata for chips & embeds."""
    tokens = list(dict.fromkeys(body.tokens))[:100]  # dedupe, cap
    items = await chess_service.resolve_chess_tokens(db, user, tokens)
    return {"items": items}


@router.get("/chess/backlinks")
async def backlinks(
    type: str = Query(..., description="Namespace: game|position|puzzle|study"),
    id: uuid.UUID = Query(..., description="Entity id"),
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("chess:read"),
):
    """Wiki pages & chess lessons that reference this chess entity."""
    if type not in chess_service.CHESS_LINK_NAMESPACES:
        raise HTTPException(400, "Unknown chess link type")
    return await chess_service.chess_backlinks(db, user, type, id)
