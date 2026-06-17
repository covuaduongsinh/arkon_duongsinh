"""Chess match WebSocket — pushes realtime state to connected players.

Endpoint: /api/chess/matches/{match_id}/ws?token=<JWT>

Browsers can't set Authorization headers on WebSockets, so the JWT is passed as
a query param (short-lived; acceptable for internal use — note for prod that the
reverse proxy must allow WS upgrades and ideally TLS). Moves are NOT sent over
this socket; clients POST moves via REST and receive the resulting state here.
"""

import asyncio
import json
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from loguru import logger

from app.database import async_session_factory
from app.database.models import Employee
from app.services import chess_match_service, chess_realtime
from app.services.auth_service import decode_access_token

router = APIRouter()


@router.websocket("/chess/matches/{match_id}/ws")
async def match_ws(websocket: WebSocket, match_id: uuid.UUID, token: str = Query(...)):
    # --- Authenticate + authorize before accepting ---
    payload = decode_access_token(token)
    if not payload:
        await websocket.close(code=4401)
        return
    async with async_session_factory() as session:
        try:
            emp = await session.get(Employee, uuid.UUID(payload["sub"]))
        except (ValueError, KeyError):
            emp = None
        match = await chess_match_service.get_match(session, match_id)
        if not emp or not match or not chess_match_service.can_access_match(emp, match):
            await websocket.close(code=4403)
            return
        initial = chess_match_service.serialize_match(match)

    await websocket.accept()
    await websocket.send_json({"type": "state", "match": initial})

    ps = await chess_realtime.subscribe(str(match_id))
    if ps is None:
        # Redis unavailable — client will fall back to polling. Keep socket open
        # but idle until the client disconnects.
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            return

    async def forward():
        async for msg in ps.listen():
            if msg.get("type") == "message":
                try:
                    data = json.loads(msg["data"])
                except (ValueError, TypeError):
                    continue
                await websocket.send_json({"type": "state", "match": data})

    async def reader():
        # Drain incoming frames to detect disconnects (clients don't send moves).
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            return

    ft = asyncio.create_task(forward())
    rt = asyncio.create_task(reader())
    try:
        _, pending = await asyncio.wait({ft, rt}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
    except Exception as e:
        logger.warning(f"match_ws error for {match_id}: {e}")
    finally:
        try:
            await ps.unsubscribe(chess_realtime.channel(str(match_id)))
            await ps.aclose()
        except Exception:
            pass
