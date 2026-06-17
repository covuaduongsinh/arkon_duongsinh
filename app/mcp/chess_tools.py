"""Arkon MCP chess tools — let Claude query the chess knowledge base.

Mirrors the wiki tools: each tool resolves the bearer-token identity, applies
the chess RBAC scope (global rows + the caller's department-scoped rows, unless
chess:read:all / admin), and returns formatted markdown. `analyze_position` is
the one tool that legitimately needs the server-side engine, since Claude has
no in-browser WASM.
"""

from typing import Optional

from fastmcp import FastMCP

from app.mcp.logging import logged_tool
from app.mcp.permissions import CAN_READ_CHESS, kb_tool


def _chess_scope_clause(model, identity):
    """Return a SQLAlchemy clause restricting `model` to the caller's scope.

    None = no restriction (admin or chess:read:all).
    """
    from sqlalchemy import or_

    if identity.is_admin or identity.has_permission("chess:read:all"):
        return None
    dept_ids = list(identity.department_ids)
    if dept_ids:
        return or_(model.scope_type != "department", model.scope_id.in_(dept_ids))
    return model.scope_type != "department"


def register_chess_tools(mcp: FastMCP):
    """Register chess KB tools on the MCP server."""

    @kb_tool(mcp, requires=CAN_READ_CHESS)
    @logged_tool("search_chess_games", query_arg="query")
    async def search_chess_games(query: str, top_k: int = 10) -> str:
        """
        Search the chess game database by player name, opening, event or ECO code.

        Args:
            query: Player, opening, event, or ECO (e.g. "Morphy", "Najdorf", "C41").
            top_k: Max games to return (default 10, max 50).

        Returns:
            A list of matching games with players, result, opening and a
            `get_chess_game(id)` hint to read the full PGN.
        """
        from app.mcp.tools import _get_identity
        identity, err = await _get_identity()
        if err:
            return err
        assert identity is not None

        top_k = min(max(1, top_k), 50)

        from sqlalchemy import or_, select
        from app.database import async_session_factory
        from app.database.models import ChessGame

        like = f"%{query}%"
        stmt = select(ChessGame).where(
            or_(
                ChessGame.white.ilike(like),
                ChessGame.black.ilike(like),
                ChessGame.opening_name.ilike(like),
                ChessGame.event.ilike(like),
                ChessGame.eco.ilike(like),
            )
        )
        clause = _chess_scope_clause(ChessGame, identity)
        if clause is not None:
            stmt = stmt.where(clause)
        stmt = stmt.order_by(ChessGame.created_at.desc()).limit(top_k)

        async with async_session_factory() as session:
            games = (await session.execute(stmt)).scalars().all()

        if not games:
            return f"No chess games found for: \"{query}\""

        lines = [f"**Chess games — {len(games)} result(s) for: \"{query}\"**\n"]
        for g in games:
            opening = f" — {g.eco or ''} {g.opening_name or ''}".rstrip()
            lines.append(
                f"- **{g.white or '?'}** vs **{g.black or '?'}** ({g.result or '*'}){opening}\n"
                f"  _Read: `get_chess_game(\"{g.id}\")`_"
            )
        return "\n".join(lines)

    @kb_tool(mcp, requires=CAN_READ_CHESS)
    @logged_tool("get_chess_game", query_arg="game_id")
    async def get_chess_game(game_id: str) -> str:
        """
        Read a single chess game's PGN and metadata by id.

        Args:
            game_id: The game UUID from `search_chess_games`.
        """
        from app.mcp.tools import _get_identity
        identity, err = await _get_identity()
        if err:
            return err
        assert identity is not None

        import uuid as uuid_mod
        from sqlalchemy import select
        from app.database import async_session_factory
        from app.database.models import ChessGame

        try:
            gid = uuid_mod.UUID(game_id)
        except ValueError:
            return f"Invalid game id: {game_id}"

        async with async_session_factory() as session:
            game = (await session.execute(
                select(ChessGame).where(ChessGame.id == gid)
            )).scalar_one_or_none()

        if not game:
            return "Game not found."
        clause = _chess_scope_clause(ChessGame, identity)
        if clause is not None and game.scope_type == "department" and game.scope_id not in identity.department_ids:
            return "Access denied — this game is scoped to a department you are not in."

        header = (
            f"**{game.white or '?'} vs {game.black or '?'}** — {game.result or '*'}\n"
            f"{game.event or ''} {game.played_at or ''} · "
            f"{game.eco or ''} {game.opening_name or ''}\n\n"
        )
        return header + "```pgn\n" + game.pgn.strip() + "\n```"

    @kb_tool(mcp, requires=CAN_READ_CHESS)
    @logged_tool("get_chess_puzzle", query_arg="theme")
    async def get_chess_puzzle(theme: Optional[str] = None) -> str:
        """
        Fetch a random published chess puzzle (optionally by theme).

        The solution is withheld unless the caller has the chess:coach grant.

        Args:
            theme: Optional theme filter (e.g. "fork", "mateIn1", "backRankMate").
        """
        from app.mcp.tools import _get_identity
        identity, err = await _get_identity()
        if err:
            return err
        assert identity is not None

        from sqlalchemy import func, select
        from app.database import async_session_factory
        from app.database.models import ChessPuzzle

        stmt = select(ChessPuzzle).where(ChessPuzzle.is_published.is_(True))
        clause = _chess_scope_clause(ChessPuzzle, identity)
        if clause is not None:
            stmt = stmt.where(clause)
        if theme:
            stmt = stmt.where(ChessPuzzle.themes.any(theme))
        stmt = stmt.order_by(func.random()).limit(1)

        async with async_session_factory() as session:
            puzzle = (await session.execute(stmt)).scalar_one_or_none()

        if not puzzle:
            return "No published puzzles found" + (f" for theme '{theme}'." if theme else ".")

        side = "White" if puzzle.side_to_move == "w" else "Black"
        out = (
            f"**{puzzle.title or 'Puzzle'}** (rating {puzzle.rating or '—'})\n"
            f"{side} to move.\n"
            f"FEN: `{puzzle.fen}`\n"
            f"Themes: {', '.join(puzzle.themes) if puzzle.themes else '—'}"
        )
        if identity.is_admin or identity.has_permission("chess:coach"):
            out += f"\n\nSolution (UCI): {' '.join(puzzle.solution_moves)}"
        return out

    @kb_tool(mcp, requires=CAN_READ_CHESS)
    @logged_tool("analyze_position", query_arg="fen")
    async def analyze_position(fen: str, depth: int = 16) -> str:
        """
        Evaluate a chess position with the server-side Stockfish engine.

        Args:
            fen: The position in FEN notation.
            depth: Search depth (default 16, capped at 22).

        Returns:
            The evaluation (centipawns from White's POV / mate), best move, and
            principal variation. If the engine is unavailable on the server,
            returns a notice instead.
        """
        from app.mcp.tools import _get_identity
        identity, err = await _get_identity()
        if err:
            return err

        from app.services import chess_engine_service, chess_service

        try:
            chess_service.validate_fen(fen)
        except ValueError as e:
            return f"Invalid FEN: {e}"

        result = await chess_engine_service.analyze_fen(fen, depth=min(max(6, depth), 22))
        if result is None:
            return (
                "The chess engine is not available on the server right now. "
                "Position is valid; analysis could not be computed."
            )
        score = (
            f"Mate in {abs(result['mate'])}" if result.get("mate") is not None
            else f"{result['eval_cp'] / 100:+.2f}"
        )
        return (
            f"**Engine analysis** (depth {result['depth']})\n"
            f"Eval (White POV): {score}\n"
            f"Best move: {result['best_move']}\n"
            f"Line: {' '.join(result['pv'][:8])}"
        )

    @kb_tool(mcp, requires=CAN_READ_CHESS)
    @logged_tool("explain_opening", query_arg="query")
    async def explain_opening(query: str) -> str:
        """
        Look up chess opening theory in the wiki (scoped to chess knowledge).

        This is a thin wrapper over the wiki search, filtered to chess content —
        use it for "what's the idea behind the Najdorf" style questions. Follow up
        with `read_wiki_page(slug)` to read a full page.

        Args:
            query: The opening or concept to explain.
        """
        from app.mcp.tools import _get_identity
        identity, err = await _get_identity()
        if err:
            return err
        assert identity is not None

        from app.ai.registry import ProviderRegistry
        from app.database import async_session_factory
        from app.services import wiki_service

        async with async_session_factory() as session:
            registry = ProviderRegistry(session)
            embedding_provider = await registry.get_embedding(task="search_query")
            query_embedding = await embedding_provider.embed(query)
            hits = await wiki_service.search_pages_semantic(
                session,
                query_embedding=query_embedding,
                top_k=8,
                allowed_kt_slugs=["chess"],
                department_ids=identity.department_ids,
                all_scopes=identity.is_admin,
            )

        if not hits:
            return (
                f"No chess wiki pages found for: \"{query}\". "
                "Opening theory may not have been imported yet."
            )
        lines = [f"**Chess wiki — {len(hits)} result(s) for: \"{query}\"**\n"]
        for page, sim in hits:
            entry = f"- `{page.slug}` — {sim:.0%}\n  **{page.title}**"
            if page.summary:
                entry += f" — {page.summary}"
            entry += f"\n  _Read: `read_wiki_page(\"{page.slug}\")`_"
            lines.append(entry)
        return "\n".join(lines)
