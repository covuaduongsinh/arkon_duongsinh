"""Server-side chess engine — drives a Stockfish binary over UCI via python-chess.

Used by the MCP `analyze_position` tool and the REST analysis endpoint (Claude
and server callers have no in-browser WASM). Bounded by depth + a hard wall
clock so a single request can't pin a worker. Degrades gracefully: if no
Stockfish binary is found, `analyze_fen` returns None and callers show a notice.

Stockfish is GPL-3.0 — it runs as a separate process (installed via the image's
apt layer), not statically linked.
"""

import asyncio
import os
import shutil
from typing import Optional

import chess
import chess.engine
from loguru import logger

# Hard ceilings so one analysis can't run away with a worker.
_MAX_DEPTH = 22
_WALL_CLOCK_S = 5.0

_engine_path_cache: Optional[str] = None
_path_resolved = False


def _find_stockfish() -> Optional[str]:
    """Locate the Stockfish binary once. Honors STOCKFISH_PATH, then PATH."""
    global _engine_path_cache, _path_resolved
    if _path_resolved:
        return _engine_path_cache
    _path_resolved = True
    candidates = [
        os.environ.get("STOCKFISH_PATH"),
        shutil.which("stockfish"),
        "/usr/games/stockfish",
        "/usr/bin/stockfish",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            _engine_path_cache = c
            break
    if _engine_path_cache:
        logger.info(f"Stockfish engine found at {_engine_path_cache}")
    else:
        logger.warning("Stockfish binary not found — server-side analysis disabled.")
    return _engine_path_cache


def _analyze_blocking(path: str, fen: str, depth: int) -> Optional[dict]:
    """Synchronous Stockfish analysis. Run via asyncio.to_thread so it never
    touches the running event loop / SQLAlchemy's async greenlet (python-chess's
    *async* engine API trips MissingGreenlet when DB IO follows in the same
    request — see analyze_fen)."""
    board = chess.Board(fen)
    with chess.engine.SimpleEngine.popen_uci(path) as engine:
        info = engine.analyse(board, chess.engine.Limit(depth=depth, time=_WALL_CLOCK_S))
    score = info["score"].white()
    pv = info.get("pv", []) or []
    return {
        "eval_cp": score.score(),          # None when it's a mate
        "mate": score.mate(),              # signed mate-in-N or None
        "best_move": pv[0].uci() if pv else None,
        "pv": [m.uci() for m in pv],
        "depth": info.get("depth", depth),
    }


async def analyze_fen(fen: str, depth: int = 16) -> Optional[dict]:
    """Analyze a FEN with Stockfish.

    Returns {eval_cp, mate, best_move, pv, depth} (eval from White's POV), or
    None if the engine is unavailable / the FEN is illegal / analysis errored.
    The engine runs in a worker thread to stay isolated from the async loop.
    """
    path = _find_stockfish()
    if not path:
        return None
    try:
        chess.Board(fen)  # validate before spawning the engine
    except ValueError:
        return None
    depth = min(max(6, depth), _MAX_DEPTH)

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_analyze_blocking, path, fen, depth),
            timeout=_WALL_CLOCK_S + 5.0,
        )
    except Exception as e:  # engine crash, timeout, illegal FEN edge cases
        logger.warning(f"Stockfish analysis failed: {e}")
        return None


def engine_available() -> bool:
    """Cheap check used by health/diagnostics and the analysis endpoint."""
    return _find_stockfish() is not None


def _analyze_game_blocking(path: str, fens: list[str], depth: int) -> list[dict]:
    """Evaluate a list of positions with ONE engine process (efficient for a
    whole game). Each entry is White-POV {eval_cp, mate, best_move}."""
    out: list[dict] = []
    with chess.engine.SimpleEngine.popen_uci(path) as engine:
        for fen in fens:
            try:
                board = chess.Board(fen)
            except ValueError:
                out.append({"eval_cp": None, "mate": None, "best_move": None})
                continue
            if board.is_game_over():
                out.append({"eval_cp": None, "mate": None, "best_move": None})
                continue
            info = engine.analyse(board, chess.engine.Limit(depth=depth))
            score = info["score"].white()
            pv = info.get("pv", []) or []
            out.append({
                "eval_cp": score.score(),
                "mate": score.mate(),
                "best_move": pv[0].uci() if pv else None,
            })
    return out


async def analyze_game(fens: list[str], depth: int = 12) -> Optional[list[dict]]:
    """Batch-evaluate every position of a game. None if engine unavailable."""
    path = _find_stockfish()
    if not path:
        return None
    depth = min(max(6, depth), _MAX_DEPTH)
    try:
        return await asyncio.to_thread(_analyze_game_blocking, path, fens, depth)
    except Exception as e:
        logger.warning(f"Stockfish game analysis failed: {e}")
        return None
