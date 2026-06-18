"""Chess service — PGN import, game/puzzle/position CRUD, puzzle scoring.

All list/read helpers apply the dual-realm scope filter via
permission_engine.build_chess_filter so callers get exactly the rows the user
may see (global rows + rows scoped to one of the user's departments, unless the
user has chess:*:all). The service never commits — routers own the transaction
(see app.database.get_db).

python-chess is the source of truth for parsing/validation: a game that does not
parse, or a FEN that is not a legal position, is rejected before it reaches the DB.
"""

import io
import uuid
from typing import Optional

import chess
import chess.pgn
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    ChessGame,
    ChessPosition,
    ChessPuzzle,
    ChessPuzzleAttempt,
    ChessStudyItem,
    ChessStudySet,
    Employee,
)
from app.services.permission_engine import build_chess_filter


# ---------------------------------------------------------------------------
# Scope helpers
# ---------------------------------------------------------------------------

def _scope_clause(model, user: Employee, action: str):
    """Return (allowed: bool, clause) for a chess model given the user's scope.

    allowed=False → user has no chess:{action} permission at all (caller should
    return an empty result). clause=None → no restriction (admin / :all).
    """
    needs_filter, allowed_dept_ids = build_chess_filter(user, action)
    if not needs_filter:
        return True, None
    if allowed_dept_ids is None:
        return False, None
    if allowed_dept_ids:
        return True, or_(
            model.scope_type != "department",
            model.scope_id.in_(allowed_dept_ids),
        )
    # own_dept but zero departments → only global rows.
    return True, model.scope_type != "department"


def resolve_scope(user: Employee, scope_type: Optional[str], scope_id: Optional[uuid.UUID]):
    """Validate a requested write scope against the user's departments.

    Returns (scope_type, scope_id). Raises ValueError if the user tries to write
    into a department they don't belong to (admins/:all bypass).
    """
    scope_type = scope_type or "global"
    if scope_type == "global":
        return "global", None
    if scope_type != "department" or scope_id is None:
        raise ValueError("Department scope requires scope_id")
    if user.role == "admin":
        return "department", scope_id
    needs_filter, allowed = build_chess_filter(user, "create")
    if not needs_filter:  # has chess:create:all
        return "department", scope_id
    if allowed and scope_id in set(allowed):
        return "department", scope_id
    raise ValueError("You cannot create chess content for that department")


# ---------------------------------------------------------------------------
# PGN parsing
# ---------------------------------------------------------------------------

def parse_pgn(pgn_text: str) -> list[dict]:
    """Parse a (possibly multi-game) PGN string into normalized game dicts.

    Each dict has: pgn, headers, white, black, result, eco, opening_name,
    white_elo, black_elo, event, played_at, ply_count, final_fen.
    Raises ValueError if no valid game is found.
    """
    games: list[dict] = []
    stream = io.StringIO(pgn_text)
    while True:
        try:
            game = chess.pgn.read_game(stream)
        except Exception as e:  # malformed token mid-stream
            raise ValueError(f"Failed to parse PGN: {e}") from e
        if game is None:
            break
        # Skip empty stubs (no moves and no players).
        headers = {k: v for k, v in game.headers.items()}
        board = game.board()
        ply = 0
        for move in game.mainline_moves():
            board.push(move)
            ply += 1
        # Skip empty stubs: python-chess returns a default-header game (White/
        # Black = "?") for non-PGN text, so treat "?"/"" as "no player".
        _w = (headers.get("White") or "").strip()
        _b = (headers.get("Black") or "").strip()
        if ply == 0 and _w in ("", "?") and _b in ("", "?"):
            continue

        def _int(val: Optional[str]) -> Optional[int]:
            try:
                return int(val) if val not in (None, "", "?") else None
            except (TypeError, ValueError):
                return None

        # Re-export so we store clean, canonical PGN.
        exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
        clean_pgn = game.accept(exporter)

        games.append({
            "pgn": clean_pgn,
            "headers": headers,
            "white": headers.get("White"),
            "black": headers.get("Black"),
            "result": headers.get("Result"),
            "eco": headers.get("ECO"),
            "opening_name": headers.get("Opening") or headers.get("Variation"),
            "white_elo": _int(headers.get("WhiteElo")),
            "black_elo": _int(headers.get("BlackElo")),
            "event": headers.get("Event"),
            "played_at": headers.get("Date") or headers.get("UTCDate"),
            "ply_count": ply,
            "final_fen": board.fen() if ply else None,
        })

    if not games:
        raise ValueError("No valid chess games found in the supplied PGN")
    return games


def validate_fen(fen: str) -> str:
    """Return the normalized FEN if legal, else raise ValueError."""
    try:
        board = chess.Board(fen)
    except ValueError as e:
        raise ValueError(f"Invalid FEN: {e}") from e
    if not board.is_valid():
        raise ValueError("FEN is not a legal position")
    return board.fen()


# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------

async def import_pgn(
    session: AsyncSession,
    user: Employee,
    pgn_text: str,
    *,
    scope_type: Optional[str] = "global",
    scope_id: Optional[uuid.UUID] = None,
    knowledge_type_slugs: Optional[list[str]] = None,
) -> list[ChessGame]:
    """Parse PGN and persist one ChessGame per game. Returns the created rows."""
    s_type, s_id = resolve_scope(user, scope_type, scope_id)
    parsed = parse_pgn(pgn_text)
    created: list[ChessGame] = []
    for g in parsed:
        game = ChessGame(
            pgn=g["pgn"],
            headers=g["headers"],
            white=g["white"],
            black=g["black"],
            result=g["result"],
            eco=g["eco"],
            opening_name=g["opening_name"],
            white_elo=g["white_elo"],
            black_elo=g["black_elo"],
            event=g["event"],
            played_at=g["played_at"],
            ply_count=g["ply_count"],
            final_fen=g["final_fen"],
            knowledge_type_slugs=knowledge_type_slugs or [],
            source_game="import",
            scope_type=s_type,
            scope_id=s_id,
            contributed_by_employee_id=user.id,
        )
        session.add(game)
        created.append(game)
    await session.flush()
    return created


async def list_games(
    session: AsyncSession,
    user: Employee,
    *,
    search: Optional[str] = None,
    eco: Optional[str] = None,
    result: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ChessGame], int]:
    allowed, clause = _scope_clause(ChessGame, user, "read")
    if not allowed:
        return [], 0

    base = select(ChessGame)
    count_base = select(func.count(ChessGame.id))
    if clause is not None:
        base = base.where(clause)
        count_base = count_base.where(clause)

    if search:
        like = f"%{search}%"
        cond = or_(
            ChessGame.white.ilike(like),
            ChessGame.black.ilike(like),
            ChessGame.opening_name.ilike(like),
            ChessGame.event.ilike(like),
        )
        base = base.where(cond)
        count_base = count_base.where(cond)
    if eco:
        base = base.where(ChessGame.eco == eco)
        count_base = count_base.where(ChessGame.eco == eco)
    if result:
        base = base.where(ChessGame.result == result)
        count_base = count_base.where(ChessGame.result == result)

    total = (await session.execute(count_base)).scalar() or 0
    offset = (max(page, 1) - 1) * page_size
    stmt = base.order_by(ChessGame.created_at.desc()).offset(offset).limit(page_size)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows), total


async def get_game(session: AsyncSession, game_id: uuid.UUID) -> Optional[ChessGame]:
    return (await session.execute(
        select(ChessGame).where(ChessGame.id == game_id)
    )).scalar_one_or_none()


def game_positions(pgn_text: str) -> tuple[list[str], list[str]]:
    """Return (fens, sans): fens has one entry per position (start + after each
    move), sans has one entry per move. len(fens) == len(sans) + 1."""
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        return [], []
    board = game.board()
    fens = [board.fen()]
    sans: list[str] = []
    for move in game.mainline_moves():
        sans.append(board.san(move))
        board.push(move)
        fens.append(board.fen())
    return fens, sans


def _cp(entry: dict) -> int:
    """White-POV centipawns, with mate mapped to a large capped value."""
    if entry.get("eval_cp") is not None:
        return int(entry["eval_cp"])
    m = entry.get("mate")
    if m is not None:
        return 30000 if m > 0 else -30000
    return 0


def build_analysis_report(sans: list[str], evals: list[dict]) -> dict:
    """Turn per-position evals into an eval graph + per-move classification.

    A move's "loss" is how much the position worsened for the mover (capped),
    classified into blunder / mistake / inaccuracy / ok.
    """
    cps = [_cp(e) for e in evals]
    moves = []
    counts = {"blunder": 0, "mistake": 0, "inaccuracy": 0}
    for i, san in enumerate(sans):
        before, after = cps[i], cps[i + 1]
        white_moved = i % 2 == 0
        loss = (before - after) if white_moved else (after - before)
        if loss >= 300:
            cls = "blunder"
        elif loss >= 150:
            cls = "mistake"
        elif loss >= 75:
            cls = "inaccuracy"
        else:
            cls = "ok"
        if cls in counts:
            counts[cls] += 1
        moves.append({
            "ply": i + 1,
            "san": san,
            "side": "white" if white_moved else "black",
            "class": cls,
        })
    return {"evals": cps, "moves": moves, "summary": counts}


async def game_to_source(session: AsyncSession, user: Employee, game: ChessGame):
    """Materialize a game as a Source so the MRP/wiki pipeline can compile theory.

    Creates a 'chess' knowledge-type Source whose full_text embeds the PGN, then
    returns it (the caller enqueues ingestion). Reuses the existing ingestion
    pipeline unchanged — chess theory becomes searchable wiki content.
    """
    from app.database.models import KnowledgeType, Source

    kt = (await session.execute(
        select(KnowledgeType).where(KnowledgeType.slug == "chess")
    )).scalar_one_or_none()

    meta_lines = [
        f"# {game.white or '?'} vs {game.black or '?'}",
        "",
        f"- Result: {game.result or '*'}",
    ]
    if game.event:
        meta_lines.append(f"- Event: {game.event}")
    if game.played_at:
        meta_lines.append(f"- Date: {game.played_at}")
    if game.eco or game.opening_name:
        meta_lines.append(f"- Opening: {game.eco or ''} {game.opening_name or ''}".rstrip())
    markdown = "\n".join(meta_lines) + "\n\n```pgn\n" + game.pgn.strip() + "\n```\n"

    source = Source(
        title=f"Chess game: {game.white or '?'} vs {game.black or '?'}",
        source_type="chess_game",
        full_text=markdown,
        status="pending",
        progress=0,
        progress_message="Queued for ingestion...",
        knowledge_type_id=kt.id if kt else None,
        contributed_by_employee_id=user.id,
        scope_type=game.scope_type,
        scope_id=game.scope_id,
    )
    session.add(source)
    await session.flush()
    return source


# ---------------------------------------------------------------------------
# Knowledge-base linkage: chess content → searchable verbatim Source
#
# Lessons / study sets are mirrored into a preserve_verbatim Source so they are
# auto-indexed into the same semantic search pool as wiki pages (search_wiki,
# explain_opening) WITHOUT running the LLM/MRP pipeline. Games keep using
# game_to_source above (full MRP compile → wiki theory). Building a curated
# wiki page is a separate, review-gated step (see the publish-wiki endpoints).
# ---------------------------------------------------------------------------

# Study-set kind → chess sub-topic knowledge-type slug (seeded in migration 042).
_STUDY_KIND_TO_KT = {
    "opening": "chess-opening",
    "tactics": "chess-tactics",
    "endgame": "chess-endgame",
    "mixed": "chess",
}


def study_kind_kt_slug(kind: str) -> str:
    """Map a study-set kind to its chess sub-topic knowledge-type slug."""
    return _STUDY_KIND_TO_KT.get(kind, "chess")


async def chess_family_kt_slugs(session: AsyncSession) -> list[str]:
    """All knowledge-type slugs in the chess family (every slug starting 'chess').

    Used to scope wiki search to chess content: the flat 'chess' type plus the
    sub-topics from migration 042 (chess-opening, chess-tactics, chess-endgame,
    chess-strategy, chess-game). Falls back to ['chess'] if not yet seeded.
    """
    from app.database.models import KnowledgeType

    slugs = list((await session.execute(
        select(KnowledgeType.slug).where(KnowledgeType.slug.like("chess%"))
    )).scalars().all())
    return slugs or ["chess"]


async def _kt_id_for_slug(session: AsyncSession, slug: str) -> Optional[uuid.UUID]:
    """Resolve a knowledge-type slug to its id, falling back to the 'chess' type."""
    from app.database.models import KnowledgeType

    kt = (await session.execute(
        select(KnowledgeType).where(KnowledgeType.slug == slug)
    )).scalar_one_or_none()
    if kt is None and slug != "chess":
        kt = (await session.execute(
            select(KnowledgeType).where(KnowledgeType.slug == "chess")
        )).scalar_one_or_none()
    return kt.id if kt else None


def build_lesson_markdown(title: str, content_md: str) -> str:
    body = (content_md or "").strip()
    return f"# {title.strip()}\n\n{body}\n" if body else f"# {title.strip()}\n"


def build_study_set_markdown(
    title: str, description: Optional[str], kind: str, notes: list[str],
) -> str:
    lines = [f"# {title.strip()}", ""]
    if description:
        lines += [description.strip(), ""]
    lines.append(f"_Loại: {kind}_")
    if notes:
        lines += ["", "## Ghi chú"] + [f"- {n.strip()}" for n in notes if n and n.strip()]
    return "\n".join(lines) + "\n"


async def _upsert_verbatim_source(
    session: AsyncSession,
    user: Employee,
    *,
    existing_id: Optional[uuid.UUID],
    title: str,
    full_text: str,
    kt_slug: str,
    scope_type: str,
    scope_id: Optional[uuid.UUID],
    source_type: str,
):
    """Create or refresh a preserve_verbatim Source mirroring chess content.

    Re-indexing an existing source resets it to 'pending' so the worker re-embeds
    the new text. Returns the Source — the caller enqueues ingestion and commits.
    """
    from app.database.models import Source

    kt_id = await _kt_id_for_slug(session, kt_slug)
    source = await session.get(Source, existing_id) if existing_id else None
    if source is None:
        source = Source(
            source_type=source_type,
            preserve_verbatim=True,
            contributed_by_employee_id=user.id,
        )
        session.add(source)
    source.title = title
    source.full_text = full_text
    source.knowledge_type_id = kt_id
    source.scope_type = scope_type
    source.scope_id = scope_id
    source.status = "pending"
    source.progress = 0
    source.progress_message = "Queued for verbatim indexing..."
    source.error_message = None
    source.page_offsets = None
    await session.flush()
    return source


async def index_chess_lesson(session: AsyncSession, user: Employee, cls, lesson):
    """(Re)index a lesson as a verbatim Source. Inherits the class's scope."""
    source = await _upsert_verbatim_source(
        session, user,
        existing_id=lesson.indexed_source_id,
        title=f"Chess lesson: {lesson.title}",
        full_text=build_lesson_markdown(lesson.title, lesson.content_md),
        kt_slug="chess-strategy",
        scope_type=cls.scope_type,
        scope_id=cls.scope_id,
        source_type="chess_lesson",
    )
    lesson.indexed_source_id = source.id
    await session.flush()
    return source


async def index_chess_study_set(session: AsyncSession, user: Employee, study: ChessStudySet):
    """(Re)index a study set as a verbatim Source (title + description + item notes)."""
    # Pull notes directly — study.items may be stale right after add_study_item.
    notes = list((await session.execute(
        select(ChessStudyItem.note)
        .where(ChessStudyItem.study_set_id == study.id, ChessStudyItem.note.isnot(None))
        .order_by(ChessStudyItem.position)
    )).scalars().all())
    source = await _upsert_verbatim_source(
        session, user,
        existing_id=study.indexed_source_id,
        title=f"Chess study set: {study.title}",
        full_text=build_study_set_markdown(study.title, study.description, study.kind, notes),
        kt_slug=_STUDY_KIND_TO_KT.get(study.kind, "chess"),
        scope_type=study.scope_type,
        scope_id=study.scope_id,
        source_type="chess_study",
    )
    study.indexed_source_id = source.id
    await session.flush()
    return source


async def enqueue_chess_index(session: AsyncSession, source) -> None:
    """Best-effort enqueue of the verbatim ingestion job for a chess Source.

    Failure to enqueue (e.g. the queue is unavailable) must NOT break the primary
    write (creating the lesson/study set) — the Source stays 'pending' and can be
    re-indexed later. The worker honours preserve_verbatim and skips the LLM.
    """
    try:
        from app.worker import get_arq_pool

        pool = await get_arq_pool()
        job = await pool.enqueue_job("ingest_map_reduce_task", str(source.id))
        if job:
            source.job_id = job.job_id
            await session.commit()
    except Exception as e:  # noqa: BLE001 — indexing is best-effort
        from loguru import logger

        logger.warning(f"enqueue_chess_index failed for source {source.id}: {e}")


async def propose_chess_wiki_page(
    session: AsyncSession,
    user: Employee,
    *,
    slug: str,
    title: str,
    content_md: str,
    kt_slug: str,
    scope_type: str,
    scope_id: Optional[uuid.UUID],
    note: Optional[str] = None,
):
    """Create a review-gated WikiPageDraft (draft_kind='create') for chess content.

    The page is NOT written directly — it lands in the wiki review queue ("Duyệt
    bài") and is materialised only when an editor approves. Reuses the existing
    draft workflow (wiki_service.create_draft). Raises ValueError if a page with
    this slug already exists in the target scope (propose an edit instead).
    """
    from app.services import wiki_service

    existing = await wiki_service.get_page_by_slug(
        session, slug, scope_type=scope_type, scope_id=scope_id,
    )
    if existing is not None:
        raise ValueError(
            f"Trang wiki '{slug}' đã tồn tại trong phạm vi này — hãy sửa trang đó thay vì tạo mới."
        )
    family = await chess_family_kt_slugs(session)
    kt_slugs = [kt_slug] if kt_slug in family else ["chess"]
    draft = await wiki_service.create_draft(
        session,
        page_id=None,
        author_id=user.id,
        content_md=content_md,
        note=note,
        source="web_ui",
        draft_kind="create",
        suggested_metadata={
            "slug": slug,
            "title": title,
            "page_type": "concept",
            "knowledge_type_slugs": kt_slugs,
            "scope_type": scope_type,
            "scope_id": str(scope_id) if scope_id else None,
        },
    )
    return draft


async def delete_game(session: AsyncSession, game: ChessGame) -> None:
    await session.delete(game)


# ---------------------------------------------------------------------------
# Puzzles
# ---------------------------------------------------------------------------

async def create_puzzle(
    session: AsyncSession,
    user: Employee,
    *,
    fen: str,
    solution_moves: list[str],
    themes: Optional[list[str]] = None,
    rating: Optional[int] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    is_published: bool = False,
    scope_type: Optional[str] = "global",
    scope_id: Optional[uuid.UUID] = None,
) -> ChessPuzzle:
    norm_fen = validate_fen(fen)
    # Validate the solution line is legal from the position.
    board = chess.Board(norm_fen)
    for uci in solution_moves:
        try:
            move = chess.Move.from_uci(uci)
        except ValueError as e:
            raise ValueError(f"Invalid UCI move '{uci}': {e}") from e
        if move not in board.legal_moves:
            raise ValueError(f"Illegal solution move '{uci}' in position {board.fen()}")
        board.push(move)

    s_type, s_id = resolve_scope(user, scope_type, scope_id)
    puzzle = ChessPuzzle(
        fen=norm_fen,
        solution_moves=solution_moves,
        side_to_move="w" if chess.Board(norm_fen).turn == chess.WHITE else "b",
        themes=themes or [],
        rating=rating,
        title=title,
        description=description,
        is_published=is_published,
        scope_type=s_type,
        scope_id=s_id,
        created_by_employee_id=user.id,
    )
    session.add(puzzle)
    await session.flush()
    return puzzle


async def list_puzzles(
    session: AsyncSession,
    user: Employee,
    *,
    theme: Optional[str] = None,
    min_rating: Optional[int] = None,
    max_rating: Optional[int] = None,
    published_only: bool = True,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ChessPuzzle], int]:
    allowed, clause = _scope_clause(ChessPuzzle, user, "read")
    if not allowed:
        return [], 0

    base = select(ChessPuzzle)
    count_base = select(func.count(ChessPuzzle.id))
    if clause is not None:
        base = base.where(clause)
        count_base = count_base.where(clause)

    # Students only ever see published puzzles; coaches can opt to see drafts.
    if published_only or not _can_coach(user):
        base = base.where(ChessPuzzle.is_published.is_(True))
        count_base = count_base.where(ChessPuzzle.is_published.is_(True))
    if theme:
        base = base.where(ChessPuzzle.themes.any(theme))
        count_base = count_base.where(ChessPuzzle.themes.any(theme))
    if min_rating is not None:
        base = base.where(ChessPuzzle.rating >= min_rating)
        count_base = count_base.where(ChessPuzzle.rating >= min_rating)
    if max_rating is not None:
        base = base.where(ChessPuzzle.rating <= max_rating)
        count_base = count_base.where(ChessPuzzle.rating <= max_rating)

    total = (await session.execute(count_base)).scalar() or 0
    offset = (max(page, 1) - 1) * page_size
    stmt = base.order_by(ChessPuzzle.created_at.desc()).offset(offset).limit(page_size)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows), total


async def get_puzzle(session: AsyncSession, puzzle_id: uuid.UUID) -> Optional[ChessPuzzle]:
    return (await session.execute(
        select(ChessPuzzle).where(ChessPuzzle.id == puzzle_id)
    )).scalar_one_or_none()


async def get_next_puzzle(
    session: AsyncSession, user: Employee, *, theme: Optional[str] = None,
) -> Optional[ChessPuzzle]:
    """Pick a published, in-scope puzzle the user hasn't solved yet (random)."""
    allowed, clause = _scope_clause(ChessPuzzle, user, "read")
    if not allowed:
        return None

    solved_subq = (
        select(ChessPuzzleAttempt.puzzle_id)
        .where(
            ChessPuzzleAttempt.employee_id == user.id,
            ChessPuzzleAttempt.solved.is_(True),
        )
    )
    stmt = select(ChessPuzzle).where(
        ChessPuzzle.is_published.is_(True),
        ChessPuzzle.id.not_in(solved_subq),
    )
    if clause is not None:
        stmt = stmt.where(clause)
    if theme:
        stmt = stmt.where(ChessPuzzle.themes.any(theme))
    stmt = stmt.order_by(func.random()).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none()


async def record_attempt(
    session: AsyncSession,
    user: Employee,
    puzzle: ChessPuzzle,
    *,
    moves_played: list[str],
    time_ms: Optional[int] = None,
    hints_used: int = 0,
) -> ChessPuzzleAttempt:
    """Validate the attempt server-side and persist it.

    `moves_played` is the full UCI line the solver reproduced (their moves and
    the auto-played replies). solved = the line exactly matches solution_moves.
    """
    solved = list(moves_played) == list(puzzle.solution_moves)

    # Elo update: student rating vs puzzle rating, K=32.
    r_before = user.puzzle_rating or 1200
    p_rating = puzzle.rating or 1200
    expected = 1.0 / (1.0 + 10 ** ((p_rating - r_before) / 400.0))
    score = 1.0 if solved else 0.0
    r_after = round(r_before + 32 * (score - expected))
    user.puzzle_rating = r_after

    attempt = ChessPuzzleAttempt(
        puzzle_id=puzzle.id,
        employee_id=user.id,
        solved=solved,
        moves_played=moves_played,
        time_ms=time_ms,
        hints_used=hints_used,
        rating_before=r_before,
        rating_after=r_after,
    )
    session.add(attempt)
    await session.flush()
    return attempt


def check_puzzle_step(solution_moves: list[str], moves_played: list[str]) -> dict:
    """Validate an in-progress multi-move puzzle attempt without revealing the
    whole solution.

    `solution_moves` is the full principal variation (solver and opponent
    alternating, solver first). `moves_played` is everything played so far
    (solver moves + the opponent replies the client already received), with the
    solver's latest move last.

    Returns {correct, solved, reply_uci}:
      - correct=False → the last solver move diverged from the solution.
      - solved=True   → the line is complete.
      - reply_uci     → the opponent's auto-reply to play next (when not solved).
    """
    n = len(moves_played)
    if list(moves_played) != list(solution_moves[:n]):
        return {"correct": False, "solved": False, "reply_uci": None}
    if n >= len(solution_moves):
        return {"correct": True, "solved": True, "reply_uci": None}
    reply = solution_moves[n]
    solved = (n + 1) >= len(solution_moves)
    return {"correct": True, "solved": solved, "reply_uci": reply}


async def puzzle_stats(session: AsyncSession, user: Employee) -> dict:
    """Aggregate the user's puzzle progress (attempts, solved, accuracy)."""
    total = (await session.execute(
        select(func.count(ChessPuzzleAttempt.id))
        .where(ChessPuzzleAttempt.employee_id == user.id)
    )).scalar() or 0
    solved = (await session.execute(
        select(func.count(func.distinct(ChessPuzzleAttempt.puzzle_id)))
        .where(
            ChessPuzzleAttempt.employee_id == user.id,
            ChessPuzzleAttempt.solved.is_(True),
        )
    )).scalar() or 0
    return {
        "attempts": total,
        "solved": solved,
        "accuracy": round(solved / total, 3) if total else 0.0,
        "rating": user.puzzle_rating or 1200,
    }


# ---------------------------------------------------------------------------
# Positions (FEN store)
# ---------------------------------------------------------------------------

async def create_position(
    session: AsyncSession,
    user: Employee,
    *,
    fen: str,
    label: Optional[str] = None,
    description: Optional[str] = None,
    themes: Optional[list[str]] = None,
    scope_type: Optional[str] = "global",
    scope_id: Optional[uuid.UUID] = None,
) -> ChessPosition:
    norm_fen = validate_fen(fen)
    s_type, s_id = resolve_scope(user, scope_type, scope_id)
    pos = ChessPosition(
        fen=norm_fen,
        label=label,
        description=description,
        themes=themes or [],
        scope_type=s_type,
        scope_id=s_id,
        created_by_employee_id=user.id,
    )
    session.add(pos)
    await session.flush()
    return pos


async def list_positions(
    session: AsyncSession, user: Employee, *, page: int = 1, page_size: int = 50,
) -> tuple[list[ChessPosition], int]:
    allowed, clause = _scope_clause(ChessPosition, user, "read")
    if not allowed:
        return [], 0
    base = select(ChessPosition)
    count_base = select(func.count(ChessPosition.id))
    if clause is not None:
        base = base.where(clause)
        count_base = count_base.where(clause)
    total = (await session.execute(count_base)).scalar() or 0
    offset = (max(page, 1) - 1) * page_size
    stmt = base.order_by(ChessPosition.created_at.desc()).offset(offset).limit(page_size)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows), total


async def get_position(session: AsyncSession, position_id: uuid.UUID) -> Optional[ChessPosition]:
    return (await session.execute(
        select(ChessPosition).where(ChessPosition.id == position_id)
    )).scalar_one_or_none()


async def delete_position(session: AsyncSession, pos: ChessPosition) -> None:
    await session.delete(pos)


# ---------------------------------------------------------------------------
# Study sets
# ---------------------------------------------------------------------------

async def create_study_set(
    session: AsyncSession,
    user: Employee,
    *,
    title: str,
    description: Optional[str] = None,
    kind: str = "mixed",
    wiki_slug: Optional[str] = None,
    scope_type: Optional[str] = "global",
    scope_id: Optional[uuid.UUID] = None,
) -> ChessStudySet:
    s_type, s_id = resolve_scope(user, scope_type, scope_id)
    study = ChessStudySet(
        title=title, description=description, kind=kind, wiki_slug=wiki_slug,
        scope_type=s_type, scope_id=s_id, created_by_employee_id=user.id,
    )
    session.add(study)
    await session.flush()
    return study


async def list_study_sets(
    session: AsyncSession, user: Employee,
) -> list[ChessStudySet]:
    allowed, clause = _scope_clause(ChessStudySet, user, "read")
    if not allowed:
        return []
    stmt = select(ChessStudySet)
    if clause is not None:
        stmt = stmt.where(clause)
    stmt = stmt.order_by(ChessStudySet.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


async def get_study_set(session: AsyncSession, set_id: uuid.UUID) -> Optional[ChessStudySet]:
    from sqlalchemy.orm import selectinload
    return (await session.execute(
        select(ChessStudySet)
        .options(selectinload(ChessStudySet.items))
        .where(ChessStudySet.id == set_id)
    )).scalar_one_or_none()


async def add_study_item(
    session: AsyncSession,
    study: ChessStudySet,
    *,
    item_type: str,
    game_id: Optional[uuid.UUID] = None,
    puzzle_id: Optional[uuid.UUID] = None,
    fen_id: Optional[uuid.UUID] = None,
    note: Optional[str] = None,
) -> ChessStudyItem:
    if item_type not in ("game", "puzzle", "fen"):
        raise ValueError("item_type must be game|puzzle|fen")
    # Append to the end.
    next_pos = (await session.execute(
        select(func.coalesce(func.max(ChessStudyItem.position), -1))
        .where(ChessStudyItem.study_set_id == study.id)
    )).scalar_one() + 1
    item = ChessStudyItem(
        study_set_id=study.id, position=next_pos, item_type=item_type,
        game_id=game_id, puzzle_id=puzzle_id, fen_id=fen_id, note=note,
    )
    session.add(item)
    await session.flush()
    return item


async def delete_study_set(session: AsyncSession, study: ChessStudySet) -> None:
    await session.delete(study)


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _can_coach(user: Employee) -> bool:
    if user.role == "admin":
        return True
    from app.services.permission_engine import _get_user_permissions
    return "chess:coach" in _get_user_permissions(user)
