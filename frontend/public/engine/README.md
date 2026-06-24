# Stockfish engine asset

The chess analysis board loads a Stockfish Web Worker from this folder
(`/engine/stockfish.js`). The engine binary is **not** checked in (it is a
large GPL WASM artifact). To enable analysis locally:

1. Download a single-threaded Stockfish WASM build (e.g. the `stockfish.js`
   single-file worker + its `.wasm`, lite/single-thread variant so no
   COOP/COEP headers are needed).
2. Place the files here as:
   - `frontend/public/engine/stockfish.js`
   - `frontend/public/engine/stockfish.wasm` (if the build is split)
3. Reload `/chess/analysis`.

## Enable via CDN (no binary committed)

Instead of self-hosting, point the engine at a CDN single-file build by setting
`NEXT_PUBLIC_STOCKFISH_URL` at build/runtime, e.g.:

```
NEXT_PUBLIC_STOCKFISH_URL=https://cdn.jsdelivr.net/npm/stockfish@16/src/stockfish-nnue-16-single.js
```

Cross-origin URLs are loaded via a same-origin blob worker that `importScripts()`
the CDN file (`src/lib/stockfishEngine.ts:createEngineWorker`). The CDN must send
permissive CORS headers (jsDelivr/unpkg do). Same-origin paths (the default
`/engine/stockfish.js`) load the Worker directly.

If the asset is absent, the Analysis panel falls back to the server-side engine
(`POST /api/chess/analysis`); if that is also unavailable it shows a notice, and
the rest of the chess module (board, PGN viewer, game library, puzzles) keeps
working.

> Licensing: Stockfish is GPL-3.0. Serving the WASM to browsers is fine for
> internal use; get legal sign-off before shipping commercially.
