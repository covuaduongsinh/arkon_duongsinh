# Chess module — production deploy checklist

The chess module (Roadmap Phases 1–3 + UI rework + Roadmap A/B/F) is ready to
deploy. **Do not deploy until the items below are confirmed.** Deploy follows the
standard Arkon recipe (push `main` → SSH to prod → `git pull` → rebuild).

## Pre-deploy gates
- [ ] **GPL legal sign-off** — see `docs/CHESS_LICENSING.md`. Decide SaaS vs.
      on-prem distribution; the latter triggers GPL-3.0 distribution duties for
      Stockfish + python-chess.
- [ ] **Student signup**: confirm whether to expose the public `/register`
      surface. It is **off by default** (`ENABLE_STUDENT_SIGNUP=false`). Leave
      off unless you intend public self-signup, and set up SMTP first if you want
      email verification (otherwise it's admin-approval / log-link only).
- [ ] **Migrations** `037_chess_module` + `038_external_users` will run on prod
      via the migrator. They are additive (new tables/columns) — no destructive
      changes. Confirm a DB backup exists before deploy.
- [ ] **Backend image** now installs `stockfish` (apt) — first prod build pulls
      it; verify the build host has registry access.
- [ ] **Tests** green: `docker exec <api> python -m pytest tests/test_chess.py -q`
      (after copying `tests/` in, or add `tests/` to the image + `pytest` to deps).

## Deploy steps (when approved)
1. Merge the chess branch to `main`, push.
2. `ssh root@5.223.55.100`
3. `sudo -u arkon bash -c 'cd /home/arkon/arkon-main && git pull'`
4. `docker compose --env-file .env.docker up -d --build`
5. Verify: migrator ran 037+038; `/api/health` healthy; `/chess` loads; seed
   games present (or import real games); Play vs Engine works.

## Post-deploy
- [ ] Decide whether to keep the **demo seed games** (5 famous games auto-seed
      when `chess_games` is empty) or replace with the club's real PGN archive.
      Remove the seed call in `app/main.py` lifespan if not wanted.
- [ ] Provision coach accounts (`global_role=knowledge_manager` → has
      `chess:coach`) and student accounts/department.

## Notes
- Realtime sparring now uses a **WebSocket** (`/api/chess/matches/{id}/ws`) backed
  by **Redis pub/sub**, with **polling as a fallback**. The reverse proxy MUST
  allow WebSocket upgrades (e.g. nginx: `proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection "upgrade"; proxy_http_version 1.1;`). If WS is
  blocked, play still works via polling. The WS auth token is passed as a query
  param — prefer TLS in prod so it isn't sent in clear text.
- The Analysis page uses the **server-side engine** (no client WASM asset
  required); do not add the GPL WASM asset unless legal sign-off covers it.
