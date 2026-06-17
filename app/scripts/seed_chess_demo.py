"""Seed a small set of famous chess games (and a couple of puzzles) for demo.

Idempotent and non-destructive: each category is seeded ONLY when its table is
empty, so it never duplicates or overwrites real content. Called from the
main.py lifespan next to seed_builtin_skills. Safe to delete entirely.
"""

from loguru import logger
from sqlalchemy import func, select

from app.database import async_session_factory
from app.database.models import ChessGame, ChessPuzzle, Employee
from app.services import chess_service

# (label, pgn) — accurate move text for well-known games. parse_pgn validates
# with python-chess and keeps the legal mainline.
_FAMOUS_GAMES: list[str] = [
    """[Event "Paris Opera"]
[Site "Paris FRA"]
[Date "1858.??.??"]
[White "Paul Morphy"]
[Black "Duke Karl / Count Isouard"]
[Result "1-0"]
[ECO "C41"]
[Opening "Philidor Defense"]

1. e4 e5 2. Nf3 d6 3. d4 Bg4 4. dxe5 Bxf3 5. Qxf3 dxe5 6. Bc4 Nf6 7. Qb3 Qe7
8. Nc3 c6 9. Bg5 b5 10. Nxb5 cxb5 11. Bxb5+ Nbd7 12. O-O-O Rd8 13. Rxd7 Rxd7
14. Rd1 Qe6 15. Bxd7+ Nxd7 16. Qb8+ Nxb8 17. Rd8# 1-0
""",
    """[Event "London"]
[Site "London ENG"]
[Date "1851.06.21"]
[White "Adolf Anderssen"]
[Black "Lionel Kieseritzky"]
[Result "1-0"]
[ECO "C33"]
[Opening "King's Gambit Accepted (Immortal Game)"]

1. e4 e5 2. f4 exf4 3. Bc4 Qh4+ 4. Kf1 b5 5. Bxb5 Nf6 6. Nf3 Qh6 7. d3 Nh5
8. Nh4 Qg5 9. Nf5 c6 10. g4 Nf6 11. Rg1 cxb5 12. h4 Qg6 13. h5 Qg5 14. Qf3 Ng8
15. Bxf4 Qf6 16. Nc3 Bc5 17. Nd5 Qxb2 18. Bd6 Bxg1 19. e5 Qxa1+ 20. Ke2 Na6
21. Nxg7+ Kd8 22. Qf6+ Nxf6 23. Be7# 1-0
""",
    """[Event "Berlin"]
[Site "Berlin GER"]
[Date "1852.??.??"]
[White "Adolf Anderssen"]
[Black "Jean Dufresne"]
[Result "1-0"]
[ECO "C52"]
[Opening "Evans Gambit (Evergreen Game)"]

1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. b4 Bxb4 5. c3 Ba5 6. d4 exd4 7. O-O d3
8. Qb3 Qf6 9. e5 Qg6 10. Re1 Nge7 11. Ba3 b5 12. Qxb5 Rb8 13. Qa4 Bb6 14. Nbd2 Bb7
15. Ne4 Qf5 16. Bxd3 Qh5 17. Nf6+ gxf6 18. exf6 Rg8 19. Rad1 Qxf3 20. Rxe7+ Nxe7
21. Qxd7+ Kxd7 22. Bf5+ Ke8 23. Bd7+ Kf8 24. Bxe7# 1-0
""",
    """[Event "Hoogovens Group A"]
[Site "Wijk aan Zee NED"]
[Date "1999.01.20"]
[White "Garry Kasparov"]
[Black "Veselin Topalov"]
[Result "1-0"]
[ECO "B07"]
[Opening "Pirc Defense (Kasparov's Immortal)"]

1. e4 d6 2. d4 Nf6 3. Nc3 g6 4. Be3 Bg7 5. Qd2 c6 6. f3 b5 7. Nge2 Nbd7
8. Bh6 Bxh6 9. Qxh6 Bb7 10. a3 e5 11. O-O-O Qe7 12. Kb1 a6 13. Nc1 O-O-O
14. Nb3 exd4 15. Rxd4 c5 16. Rd1 Nb6 17. g3 Kb8 18. Na5 Ba8 19. Bh3 d5
20. Qf4+ Ka7 21. Rhe1 d4 22. Nd5 Nbxd5 23. exd5 Qd6 24. Rxd4 cxd4 25. Re7+ Kb6
26. Qxd4+ Kxa5 27. b4+ Ka4 28. Qc3 Qxd5 29. Ra7 Bb7 30. Rxb7 Qc4 31. Qxf6 Kxa3
32. Qxa6+ Kxb4 33. c3+ Kxc3 34. Qa1+ Kd2 35. Qb2+ Kd1 36. Bf1 Rd2 37. Rd7 Rxd7
38. Bxc4 bxc4 39. Qxh8 Rd3 40. Qa8 c3 41. Qa4+ Ke1 42. f4 f5 43. Kc1 Rd2
44. Qa7 1-0
""",
    """[Event "World Championship"]
[Site "Reykjavik ISL"]
[Date "1972.07.23"]
[White "Robert J. Fischer"]
[Black "Boris Spassky"]
[Result "1-0"]
[ECO "D59"]
[Opening "QGD Tartakower (WCh Game 6)"]

1. c4 e6 2. Nf3 d5 3. d4 Nf6 4. Nc3 Be7 5. Bg5 O-O 6. e3 h6 7. Bh4 b6
8. cxd5 Nxd5 9. Bxe7 Qxe7 10. Nxd5 exd5 11. Rc1 Be6 12. Qa4 c5 13. Qa3 Rc8
14. Bb5 a6 15. dxc5 bxc5 16. O-O Ra7 17. Be2 Nd7 18. Nd4 Qf8 19. Nxe6 fxe6
20. e4 d4 21. f4 Qe7 22. e5 Rb8 23. Bc4 Kh8 24. Qh3 Nf8 25. b3 a5 26. f5 exf5
27. Rxf5 Nh7 28. Rcf1 Qd8 29. Qg3 Re7 30. h4 Rbb7 31. e6 Rbc7 32. Qe5 Qe8
33. a4 Qd8 34. R1f2 Qe8 35. R2f3 Qd8 36. Bd3 Qe8 37. Qe4 Nf6 38. Rxf6 gxf6
39. Rxf6 Kg8 40. Bc4 Kh8 41. Qf4 1-0
""",
]


async def seed_chess_demo() -> None:
    """Insert demo games/puzzles when the chess tables are empty."""
    try:
        async with async_session_factory() as session:
            admin = (await session.execute(
                select(Employee).where(Employee.role == "admin").limit(1)
            )).scalar_one_or_none()
            admin_id = admin.id if admin else None

            game_count = (await session.execute(
                select(func.count(ChessGame.id))
            )).scalar() or 0
            if game_count == 0:
                inserted = 0
                for pgn in _FAMOUS_GAMES:
                    try:
                        parsed = chess_service.parse_pgn(pgn)
                    except ValueError:
                        continue
                    for g in parsed:
                        session.add(ChessGame(
                            pgn=g["pgn"], headers=g["headers"], white=g["white"],
                            black=g["black"], result=g["result"], eco=g["eco"],
                            opening_name=g["opening_name"], white_elo=g["white_elo"],
                            black_elo=g["black_elo"], event=g["event"],
                            played_at=g["played_at"], ply_count=g["ply_count"],
                            final_fen=g["final_fen"], knowledge_type_slugs=["chess"],
                            source_game="import", scope_type="global",
                            contributed_by_employee_id=admin_id,
                        ))
                        inserted += 1
                await session.commit()
                logger.success(f"Seeded {inserted} demo chess game(s)")

            puzzle_count = (await session.execute(
                select(func.count(ChessPuzzle.id))
            )).scalar() or 0
            if puzzle_count == 0:
                demo_puzzles = [
                    {
                        "fen": "6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1",
                        "solution_moves": ["d1d8"],
                        "themes": ["backRankMate", "mateIn1"],
                        "rating": 800, "title": "Back-rank mate",
                        "description": "White to move and mate in one.",
                    },
                    {
                        "fen": "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 0 1",
                        "solution_moves": ["h5f7"],
                        "themes": ["mateIn1", "scholarsMate"],
                        "rating": 700, "title": "Scholar's mate",
                        "description": "White to move and mate in one.",
                    },
                ]
                added = 0
                for p in demo_puzzles:
                    try:
                        chess_service.validate_fen(p["fen"])
                    except ValueError:
                        continue
                    session.add(ChessPuzzle(
                        fen=p["fen"], solution_moves=p["solution_moves"],
                        side_to_move="w", themes=p["themes"], rating=p["rating"],
                        title=p["title"], description=p["description"],
                        is_published=True, scope_type="global",
                        created_by_employee_id=admin_id,
                    ))
                    added += 1
                await session.commit()
                logger.success(f"Seeded {added} demo chess puzzle(s)")
    except Exception as e:  # never block startup on demo seeding
        logger.warning(f"Could not seed chess demo content: {e}")
