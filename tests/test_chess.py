"""Unit tests for the chess module's pure logic (no DB required).

Run inside the api container where deps are installed:
    docker exec arkon_api python -m pytest tests/test_chess.py -q
"""

import types

import pytest

from app.database.models import ChessMatch, Employee
from app.services import chess_service
from app.services import chess_match_service as ms
from app.services import permissions as perms
from app.services.permission_engine import build_chess_filter, can_access_chess

OPERA_PGN = """[Event "Paris Opera"]
[White "Paul Morphy"]
[Black "Duke Karl"]
[Result "1-0"]
[ECO "C41"]
[Opening "Philidor Defense"]

1. e4 e5 2. Nf3 d6 3. d4 Bg4 4. dxe5 Bxf3 5. Qxf3 dxe5 6. Bc4 Nf6 7. Qb3 Qe7
8. Nc3 c6 9. Bg5 b5 10. Nxb5 cxb5 11. Bxb5+ Nbd7 12. O-O-O Rd8 13. Rxd7 Rxd7
14. Rd1 Qe6 15. Bxd7+ Nxd7 16. Qb8+ Nxb8 17. Rd8# 1-0
"""

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


# ── PGN parsing ──

def test_parse_pgn_opera_game():
    games = chess_service.parse_pgn(OPERA_PGN)
    assert len(games) == 1
    g = games[0]
    assert g["white"] == "Paul Morphy"
    assert g["black"] == "Duke Karl"
    assert g["result"] == "1-0"
    assert g["eco"] == "C41"
    assert g["ply_count"] == 33  # 17 moves, mate on move 17 for white
    assert g["final_fen"] and g["final_fen"].endswith("b k - 1 17")


def test_parse_pgn_multi_game():
    games = chess_service.parse_pgn(OPERA_PGN + "\n\n" + OPERA_PGN)
    assert len(games) == 2


def test_parse_pgn_invalid_raises():
    with pytest.raises(ValueError):
        chess_service.parse_pgn("this is not pgn at all")


# ── FEN validation ──

def test_validate_fen_ok():
    assert chess_service.validate_fen(START_FEN).startswith("rnbqkbnr")


def test_validate_fen_bad():
    with pytest.raises(ValueError):
        chess_service.validate_fen("not-a-fen")


# ── RBAC filters ──

def _user(role="employee", global_role="viewer"):
    return Employee(name="t", email="t@x.com", role=role, global_role=global_role)


def test_build_chess_filter_admin_unrestricted():
    needs, depts = build_chess_filter(_user(role="admin"), "read")
    assert needs is False and depts == []


def test_build_chess_filter_all_scope_unrestricted():
    # knowledge_manager has chess:read:all
    needs, depts = build_chess_filter(_user(global_role="knowledge_manager"), "read")
    assert needs is False


def test_build_chess_filter_own_dept():
    # student has chess:read:own_dept; no departments -> only global rows
    needs, depts = build_chess_filter(_user(global_role="student"), "read")
    assert needs is True and depts == []


def test_build_chess_filter_no_permission():
    # viewer has no chess:create
    needs, depts = build_chess_filter(_user(global_role="viewer"), "create")
    assert needs is True and depts is None


def test_can_access_chess_global_visible():
    obj = types.SimpleNamespace(scope_type="global", scope_id=None)
    assert can_access_chess(_user(global_role="student"), obj, "read") is True


def test_can_access_chess_other_department_denied():
    import uuid
    obj = types.SimpleNamespace(scope_type="department", scope_id=uuid.uuid4())
    assert can_access_chess(_user(global_role="student"), obj, "read") is False


def test_can_access_chess_admin_always():
    import uuid
    obj = types.SimpleNamespace(scope_type="department", scope_id=uuid.uuid4())
    assert can_access_chess(_user(role="admin"), obj, "delete") is True


# ── Permissions catalog ──

def test_check_puzzle_step_multi_move():
    sol = ["e2e4", "e7e5", "g1f3"]  # solver e4, reply e5, solver Nf3
    # solver's first move correct → reply with opponent's e5, not solved yet
    r1 = chess_service.check_puzzle_step(sol, ["e2e4"])
    assert r1 == {"correct": True, "solved": False, "reply_uci": "e7e5"}
    # solver completes the line → solved
    r2 = chess_service.check_puzzle_step(sol, ["e2e4", "e7e5", "g1f3"])
    assert r2["correct"] is True and r2["solved"] is True
    # wrong final move
    r3 = chess_service.check_puzzle_step(sol, ["e2e4", "e7e5", "b1c3"])
    assert r3["correct"] is False and r3["solved"] is False


def test_game_positions_and_report():
    fens, sans = chess_service.game_positions(OPERA_PGN)
    assert len(sans) == 33 and len(fens) == 34
    # Fabricate evals: flat 20cp, then a big drop at ply 3 (white blunders).
    evals = [{"eval_cp": 20, "mate": None, "best_move": None} for _ in fens]
    evals[3] = {"eval_cp": -400, "mate": None, "best_move": None}  # after move 3 (black to move)
    report = chess_service.build_analysis_report(sans, evals)
    assert len(report["evals"]) == len(fens)
    assert len(report["moves"]) == len(sans)
    # ply 3 is white's move (index 2) going from +20 to -400 -> blunder
    assert report["moves"][2]["class"] == "blunder"
    assert report["summary"]["blunder"] >= 1


def test_chess_permissions_registered():
    for p in ("chess:read:all", "chess:play", "chess:coach", "chess:create:own_dept"):
        assert p in perms.ALL_PERMISSIONS
    assert "student" in perms.ROLE_PERMISSIONS_MAP
    assert "chess:play" in perms.ROLE_PERMISSIONS_MAP["student"]


# ── Knowledge-base linkage helpers (no DB) ──

def test_study_kind_kt_slug_maps_subtopics():
    assert chess_service.study_kind_kt_slug("opening") == "chess-opening"
    assert chess_service.study_kind_kt_slug("tactics") == "chess-tactics"
    assert chess_service.study_kind_kt_slug("endgame") == "chess-endgame"
    # mixed and unknown kinds fall back to the flat 'chess' type
    assert chess_service.study_kind_kt_slug("mixed") == "chess"
    assert chess_service.study_kind_kt_slug("whatever") == "chess"


def test_build_lesson_markdown_has_title_and_body():
    md = chess_service.build_lesson_markdown("Najdorf basics", "Play ...a6 then ...e5.")
    assert md.startswith("# Najdorf basics")
    assert "Play ...a6" in md
    # empty body still produces a heading (so the verbatim source is searchable)
    assert chess_service.build_lesson_markdown("Empty", "  ").strip() == "# Empty"


def test_build_study_set_markdown_includes_parts():
    md = chess_service.build_study_set_markdown(
        "Endgame drills", "Rook endings.", "endgame", ["Cut the king off", ""],
    )
    assert "# Endgame drills" in md
    assert "Rook endings." in md
    assert "_Loại: endgame_" in md
    assert "- Cut the king off" in md  # non-empty notes are listed
    assert md.count("- ") == 1  # blank note is dropped


# ── Knowledge-gap chess labeling (no DB) ──

def test_is_chess_query_classifier():
    from app.services.stats_aggregator import _is_chess_query

    assert _is_chess_query("khai cuoc sicilian najdorf") is True
    assert _is_chess_query("endgame rook technique") is True
    assert _is_chess_query("how to analyze a pgn file") is True
    assert _is_chess_query("chinh sach nghi phep cong ty") is False
    assert _is_chess_query("quarterly revenue report") is False


# ── Match logic (no DB) ──

def test_turn_color():
    assert ms._turn_color(START_FEN) == "white"


def test_record_move_and_finish_scholars_mate():
    import chess
    # Position one move before Scholar's mate: White Qh5xf7#
    fen = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 0 1"
    match = ChessMatch(mode="human_vs_human", status="active", current_fen=fen, moves=[])
    board = chess.Board(fen)
    move = chess.Move.from_uci("h5f7")
    board2 = ms._record_move(match, board, move, by="white")
    assert match.moves[-1]["san"].startswith("Qxf7")
    assert match.current_fen == board2.fen()
    ended = ms._maybe_finish(match, board2)
    assert ended is True
    assert match.status == "finished"
    assert match.result == "1-0"


# ── Lichess puzzle import — pure mapping/filter/validate (no DB) ──

# One representative row as csv.DictReader would yield it (black to move FEN).
_LICHESS_ROW = {
    "PuzzleId": "00sHx",
    "FEN": "q3k1nr/1pp1nQpp/3p4/1P2p3/4P3/B1PP1b2/B5PP/5K2 b k - 0 17",
    "Moves": "e8d7 a2e6 d7d8 f7f8",
    "Rating": "1760",
    "RatingDeviation": "80",
    "Popularity": "93",
    "NbPlays": "1234",
    "Themes": "mate mateIn2 middlegame short",
    "GameUrl": "https://lichess.org/yyznGmXs/black#34",
    "OpeningTags": "Italian_Game Italian_Game_Classical_Variation",
}


def test_lichess_row_to_values_normalizes_lead_in():
    from app.services import chess_service
    from app.services.puzzle_import_service import row_to_values

    v = row_to_values(_LICHESS_ROW)
    assert v is not None
    assert v["slug"] == "lichess-00shx"  # lower-cased PuzzleId
    assert v["lichess_id"] == "00sHx"
    assert v["source"] == "lichess"
    # The opponent's lead-in move (Moves[0]) is split out; the solver finds Moves[1:].
    assert v["setup_move"] == "e8d7"
    assert v["setup_fen"] == _LICHESS_ROW["FEN"]
    assert v["solution_moves"] == ["a2e6", "d7d8", "f7f8"]
    # fen is now the solve position (after the lead-in move) — solver = White to move.
    assert v["fen"] == chess_service.apply_uci_to_fen(_LICHESS_ROW["FEN"], "e8d7")
    assert v["side_to_move"] == "w"
    assert v["themes"] == ["mate", "mateIn2", "middlegame", "short"]
    assert v["rating"] == 1760 and v["popularity"] == 93 and v["nb_plays"] == 1234
    assert v["opening_name"] == "Italian Game Classical Variation"
    assert v["is_published"] is False
    assert isinstance(v["piece_count"], int) and v["piece_count"] > 0


def test_lichess_row_to_values_skips_blank_fen():
    from app.services.puzzle_import_service import row_to_values

    assert row_to_values({"PuzzleId": "x", "FEN": "  "}) is None


def test_lichess_row_to_values_skips_single_move():
    from app.services.puzzle_import_service import row_to_values

    # A valid Lichess puzzle needs the lead-in move + at least one solution move.
    row = dict(_LICHESS_ROW, Moves="e8d7")
    assert row_to_values(row) is None


def test_apply_uci_to_fen():
    # Legal move flips the side to move; illegal/garbage returns None.
    after = chess_service.apply_uci_to_fen(START_FEN, "e2e4")
    assert after is not None and after.split()[1] == "b"
    assert chess_service.apply_uci_to_fen(START_FEN, "e2e5") is None  # illegal pawn jump
    assert chess_service.apply_uci_to_fen("not-a-fen", "e2e4") is None


def test_lichess_passes_filters():
    from app.services.puzzle_import_service import PuzzleImportFilters, passes_filters

    assert passes_filters(_LICHESS_ROW, PuzzleImportFilters(min_rating=1700, max_rating=1800))
    assert not passes_filters(_LICHESS_ROW, PuzzleImportFilters(min_rating=1800))
    assert not passes_filters(_LICHESS_ROW, PuzzleImportFilters(max_rating=1700))
    assert passes_filters(_LICHESS_ROW, PuzzleImportFilters(theme="mateIn2"))
    assert not passes_filters(_LICHESS_ROW, PuzzleImportFilters(theme="fork"))
    assert passes_filters(_LICHESS_ROW, PuzzleImportFilters(opening="italian"))
    assert not passes_filters(_LICHESS_ROW, PuzzleImportFilters(opening="sicilian"))


def test_validate_filters_guards_unbounded_import():
    from app.services.puzzle_import_service import (
        MAX_IMPORT_LIMIT,
        PuzzleImportFilters,
        validate_filters,
    )

    # No filter and no limit → refuse (would import the whole ~5M dump).
    with pytest.raises(ValueError):
        validate_filters(PuzzleImportFilters())
    # Over the hard cap → refuse.
    with pytest.raises(ValueError):
        validate_filters(PuzzleImportFilters(limit=MAX_IMPORT_LIMIT + 1))
    # A rating filter alone is enough; a sane limit alone is enough.
    validate_filters(PuzzleImportFilters(min_rating=1500))
    validate_filters(PuzzleImportFilters(limit=5000))
