"""Chess sparring matches — human-vs-engine and human-vs-human.

State lives on the ChessMatch row (`current_fen` + `moves` JSONB), which the
frontend reads by polling GET /matches/{id}. Move legality is validated with
python-chess; for human-vs-engine the server plays the reply with Stockfish
(falling back to a random legal move if the engine is unavailable). When the
game ends, the match is archived into a ChessGame (source_game="sparring").

No new realtime infra: polling is sufficient for the expected volume. A
websocket + Redis pub/sub layer can be added later without changing this model.
"""

import random
import uuid
from typing import Optional

import chess
import chess.pgn
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import CHESS_START_FEN, ChessGame, ChessMatch, Employee

# engine_level (1..8) → search depth for the reply. Higher = stronger/slower.
_LEVEL_DEPTH = {1: 1, 2: 3, 3: 5, 4: 7, 5: 9, 6: 11, 7: 14, 8: 18}


def _turn_color(fen: str) -> str:
    return "white" if chess.Board(fen).turn == chess.WHITE else "black"


def _side_employee(match: ChessMatch, color: str) -> Optional[uuid.UUID]:
    return match.white_employee_id if color == "white" else match.black_employee_id


async def create_match(
    session: AsyncSession,
    user: Employee,
    *,
    mode: str = "human_vs_engine",
    player_color: str = "white",
    engine_level: int = 4,
) -> ChessMatch:
    """Create a match. For human_vs_engine the user takes `player_color`; the
    engine takes the other side (null employee) and moves first if it is White.
    """
    if mode not in ("human_vs_engine", "human_vs_human"):
        raise ValueError("mode must be human_vs_engine or human_vs_human")
    if player_color not in ("white", "black"):
        raise ValueError("player_color must be white or black")

    white_id = user.id if player_color == "white" else None
    black_id = user.id if player_color == "black" else None
    # For human_vs_human the opponent joins later (kept null = open seat); for
    # human_vs_engine the opposite seat stays null = the engine.

    match = ChessMatch(
        white_employee_id=white_id,
        black_employee_id=black_id,
        mode=mode,
        engine_level=engine_level if mode == "human_vs_engine" else None,
        status="active",
        current_fen=CHESS_START_FEN,
        moves=[],
        scope_type="global",
    )
    session.add(match)
    await session.flush()

    # Engine plays first if it has White.
    if mode == "human_vs_engine" and player_color == "black":
        await _engine_reply(session, match)

    return match


async def get_match(session: AsyncSession, match_id: uuid.UUID) -> Optional[ChessMatch]:
    return (await session.execute(
        select(ChessMatch).where(ChessMatch.id == match_id)
    )).scalar_one_or_none()


async def list_matches(session: AsyncSession, user: Employee) -> list[ChessMatch]:
    stmt = (
        select(ChessMatch)
        .where(or_(
            ChessMatch.white_employee_id == user.id,
            ChessMatch.black_employee_id == user.id,
        ))
        .order_by(ChessMatch.updated_at.desc())
        .limit(50)
    )
    return list((await session.execute(stmt)).scalars().all())


def can_access_match(user: Employee, match: ChessMatch) -> bool:
    return (
        user.role == "admin"
        or match.white_employee_id == user.id
        or match.black_employee_id == user.id
    )


def serialize_match(match: ChessMatch) -> dict:
    """Match state for realtime publish (no per-viewer `your_color`)."""
    return {
        "id": str(match.id),
        "white_employee_id": str(match.white_employee_id) if match.white_employee_id else None,
        "black_employee_id": str(match.black_employee_id) if match.black_employee_id else None,
        "mode": match.mode,
        "engine_level": match.engine_level,
        "status": match.status,
        "current_fen": match.current_fen,
        "moves": list(match.moves or []),
        "result": match.result,
        "winner_employee_id": str(match.winner_employee_id) if match.winner_employee_id else None,
        "game_id": str(match.game_id) if match.game_id else None,
    }


async def list_open_matches(session: AsyncSession, user: Employee) -> list[ChessMatch]:
    """Joinable human-vs-human matches: active, one empty seat, not the user's."""
    stmt = (
        select(ChessMatch)
        .where(
            ChessMatch.mode == "human_vs_human",
            ChessMatch.status == "active",
            or_(
                ChessMatch.white_employee_id.is_(None),
                ChessMatch.black_employee_id.is_(None),
            ),
            ChessMatch.white_employee_id.isnot(None) | ChessMatch.black_employee_id.isnot(None),
        )
        .order_by(ChessMatch.created_at.desc())
        .limit(50)
    )
    rows = (await session.execute(stmt)).scalars().all()
    # Exclude matches the user already sits in.
    return [m for m in rows if user.id not in (m.white_employee_id, m.black_employee_id)]


async def join_match(session: AsyncSession, match: ChessMatch, user: Employee) -> ChessMatch:
    """Claim the open seat of a human-vs-human match."""
    if match.mode != "human_vs_human":
        raise ValueError("Chỉ tham gia được ván người-với-người")
    if match.status != "active":
        raise ValueError("Ván không còn mở")
    if user.id in (match.white_employee_id, match.black_employee_id):
        raise ValueError("Bạn đã ở trong ván này")
    if match.white_employee_id is None:
        match.white_employee_id = user.id
    elif match.black_employee_id is None:
        match.black_employee_id = user.id
    else:
        raise ValueError("Ván đã đủ người")
    await session.flush()
    return match


def _record_move(match: ChessMatch, board_before: chess.Board, move: chess.Move, by: str) -> chess.Board:
    san = board_before.san(move)
    board_before.push(move)
    match.moves = list(match.moves) + [{
        "uci": move.uci(),
        "san": san,
        "fen": board_before.fen(),
        "by": by,
    }]
    match.current_fen = board_before.fen()
    return board_before


def _maybe_finish(match: ChessMatch, board: chess.Board) -> bool:
    """If the position is terminal, mark the match finished. Returns True if ended."""
    if not board.is_game_over():
        return False
    outcome = board.outcome()
    if outcome is None:
        return False
    if outcome.winner is None:
        match.result = "1/2-1/2"
        match.winner_employee_id = None
    elif outcome.winner == chess.WHITE:
        match.result = "1-0"
        match.winner_employee_id = match.white_employee_id
    else:
        match.result = "0-1"
        match.winner_employee_id = match.black_employee_id
    match.status = "finished"
    return True


async def _engine_reply(session: AsyncSession, match: ChessMatch) -> None:
    """Play the engine's move on the current position (human_vs_engine only)."""
    from app.services import chess_engine_service

    board = chess.Board(match.current_fen)
    if board.is_game_over():
        _maybe_finish(match, board)
        return

    depth = _LEVEL_DEPTH.get(match.engine_level or 4, 7)
    result = await chess_engine_service.analyze_fen(match.current_fen, depth=depth)
    move: Optional[chess.Move] = None
    if result and result.get("best_move"):
        try:
            cand = chess.Move.from_uci(result["best_move"])
            if cand in board.legal_moves:
                move = cand
        except ValueError:
            move = None
    if move is None:
        # Engine unavailable / no move — fall back to a random legal move so
        # the game can still proceed.
        legal = list(board.legal_moves)
        if not legal:
            _maybe_finish(match, board)
            return
        move = random.choice(legal)

    board = _record_move(match, board, move, by="engine")
    _maybe_finish(match, board)


async def apply_move(
    session: AsyncSession, match: ChessMatch, user: Employee, uci: str,
) -> ChessMatch:
    """Validate and apply the user's move; for vs-engine, play the engine reply."""
    if match.status != "active":
        raise ValueError("Match is not active")

    board = chess.Board(match.current_fen)
    color = _turn_color(match.current_fen)
    expected = _side_employee(match, color)

    # human_vs_human open seat: the first opponent to move claims the seat.
    if expected is None and match.mode == "human_vs_human":
        if color == "white":
            match.white_employee_id = user.id
        else:
            match.black_employee_id = user.id
        expected = user.id

    if expected is None:
        raise ValueError("It is the engine's turn")
    if expected != user.id and user.role != "admin":
        raise ValueError("It is not your turn")

    try:
        move = chess.Move.from_uci(uci)
    except ValueError as e:
        raise ValueError(f"Invalid move '{uci}': {e}") from e
    if move not in board.legal_moves:
        raise ValueError(f"Illegal move '{uci}'")

    board = _record_move(match, board, move, by=color)
    ended = _maybe_finish(match, board)

    if not ended and match.mode == "human_vs_engine":
        await _engine_reply(session, match)

    if match.status == "finished":
        await _archive(session, match)

    await session.flush()
    return match


async def resign(session: AsyncSession, match: ChessMatch, user: Employee) -> ChessMatch:
    if match.status != "active":
        raise ValueError("Match is not active")
    # Resigning hands the win to the other side.
    if match.white_employee_id == user.id:
        match.result, match.winner_employee_id = "0-1", match.black_employee_id
    elif match.black_employee_id == user.id:
        match.result, match.winner_employee_id = "1-0", match.white_employee_id
    else:
        raise ValueError("You are not a player in this match")
    match.status = "finished"
    await _archive(session, match)
    await session.flush()
    return match


async def _player_name(session: AsyncSession, emp_id: Optional[uuid.UUID]) -> str:
    if emp_id is None:
        return "Engine"
    emp = (await session.execute(
        select(Employee).where(Employee.id == emp_id)
    )).scalar_one_or_none()
    return emp.name if emp else "Player"


async def _archive(session: AsyncSession, match: ChessMatch) -> None:
    """Write the finished match into the ChessGame archive (idempotent)."""
    if match.game_id is not None:
        return
    game = chess.pgn.Game()
    white = await _player_name(session, match.white_employee_id)
    black = await _player_name(session, match.black_employee_id)
    game.headers["Event"] = "Arkon sparring"
    game.headers["White"] = white
    game.headers["Black"] = black
    game.headers["Result"] = match.result or "*"

    node = game
    board = chess.Board()
    for mv in match.moves:
        try:
            move = chess.Move.from_uci(mv["uci"])
        except (ValueError, KeyError, TypeError):
            break
        node = node.add_variation(move)
        board.push(move)
    exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
    pgn = game.accept(exporter)

    archived = ChessGame(
        pgn=pgn,
        headers={"White": white, "Black": black, "Result": match.result or "*"},
        white=white,
        black=black,
        result=match.result,
        ply_count=len(match.moves),
        final_fen=match.current_fen,
        source_game="sparring",
        match_id=match.id,
        scope_type=match.scope_type,
        scope_id=match.scope_id,
        contributed_by_employee_id=match.white_employee_id or match.black_employee_id,
    )
    session.add(archived)
    await session.flush()
    match.game_id = archived.id
