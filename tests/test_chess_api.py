"""Integration tests for the chess REST API — real DB, real auth, real routing.

Covers the highest-value paths and the permission/scope boundaries that pure
unit tests cannot reach:
  * PGN import (happy path + permission gate)
  * puzzle create → solve → Elo update
  * department scope isolation (a student only sees global + own-department rows)

These complement the pure-logic tests in ``tests/test_chess.py``.
"""

OPERA_PGN = """[Event "Paris Opera"]
[White "Paul Morphy"]
[Black "Duke Karl"]
[Result "1-0"]
[ECO "C41"]

1. e4 e5 2. Nf3 d6 3. d4 Bg4 4. dxe5 Bxf3 5. Qxf3 dxe5 6. Bc4 Nf6 7. Qb3 Qe7
8. Nc3 c6 9. Bg5 b5 10. Nxb5 cxb5 11. Bxb5+ Nbd7 12. O-O-O Rd8 13. Rxd7 Rxd7
14. Rd1 Qe6 15. Bxd7+ Nxd7 16. Qb8+ Nxb8 17. Rd8# 1-0
"""

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


# ── PGN import ──────────────────────────────────────────────────────────────


async def test_import_game_as_admin(client, make_user):
    _, headers = await make_user(role="admin")
    r = await client.post(
        "/api/chess/games/import",
        data={"pgn": OPERA_PGN, "scope_type": "global"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["imported"] == 1
    assert body["items"][0]["white"] == "Paul Morphy"


async def test_import_game_forbidden_for_viewer(client, make_user):
    # A plain viewer has no chess:create permission.
    _, headers = await make_user(global_role="viewer")
    r = await client.post(
        "/api/chess/games/import",
        data={"pgn": OPERA_PGN, "scope_type": "global"},
        headers=headers,
    )
    assert r.status_code == 403


async def test_import_requires_auth(client):
    r = await client.post(
        "/api/chess/games/import",
        data={"pgn": OPERA_PGN, "scope_type": "global"},
    )
    assert r.status_code == 401


# ── Puzzle create → solve → Elo ─────────────────────────────────────────────


async def test_create_and_solve_puzzle_updates_elo(client, db, make_user):
    _, coach_headers = await make_user(role="admin")
    student, student_headers = await make_user(global_role="student")

    # Coach creates a published one-move puzzle (1.e4 from the start position).
    r = await client.post(
        "/api/chess/puzzles",
        json={
            "fen": START_FEN,
            "solution_moves": ["e2e4"],
            "themes": ["opening"],
            "rating": 1200,
            "is_published": True,
            "scope_type": "global",
        },
        headers=coach_headers,
    )
    assert r.status_code == 200, r.text
    puzzle_id = r.json()["id"]

    # Student solves it with the correct move.
    r = await client.post(
        f"/api/chess/puzzles/{puzzle_id}/attempt",
        json={"moves_played": ["e2e4"], "time_ms": 3000, "hints_used": 0},
        headers=student_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["solved"] is True

    # The terminal attempt updated the student's Elo away from the 1200 default.
    await db.refresh(student)
    assert student.puzzle_rating != 1200


async def test_student_cannot_publish_puzzle(client, make_user):
    _, headers = await make_user(global_role="student")
    r = await client.post(
        "/api/chess/puzzles",
        json={
            "fen": START_FEN,
            "solution_moves": ["e2e4"],
            "is_published": True,
            "scope_type": "global",
        },
        headers=headers,
    )
    # Students lack chess:create entirely → 403 (never reaches the publish gate).
    assert r.status_code == 403


# ── Department scope isolation ──────────────────────────────────────────────


async def _import(client, headers, *, scope_type, scope_id=None):
    data = {"pgn": OPERA_PGN, "scope_type": scope_type}
    if scope_id is not None:
        data["scope_id"] = str(scope_id)
    r = await client.post("/api/chess/games/import", data=data, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["items"][0]["id"]


async def test_scope_isolation_between_departments(
    client, make_user, make_department
):
    dept_a = await make_department("Dept A")
    dept_b = await make_department("Dept B")

    _, admin_headers = await _admin(client, make_user)
    global_id = await _import(client, admin_headers, scope_type="global")
    a_id = await _import(client, admin_headers, scope_type="department", scope_id=dept_a.id)
    b_id = await _import(client, admin_headers, scope_type="department", scope_id=dept_b.id)

    # Publish all three so the student-visible filter is purely about scope.
    r = await client.post(
        "/api/chess/games/bulk-publish",
        json={"ids": [global_id, a_id, b_id], "publish": True},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text

    # A student in Dept A sees the global row + Dept A, but not Dept B.
    _, student_headers = await make_user(global_role="student", departments=[dept_a])
    r = await client.get("/api/chess/games", headers=student_headers)
    assert r.status_code == 200, r.text
    visible = {item["id"] for item in r.json()["items"]}
    assert global_id in visible
    assert a_id in visible
    assert b_id not in visible


async def _admin(client, make_user):
    return await make_user(role="admin")
