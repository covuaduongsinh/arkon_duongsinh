# Chess module — third-party licensing notes

This document summarizes the licenses of the third-party chess components used
by the Arkon chess module, and the obligations to review **before shipping
commercially**. This is engineering guidance, not legal advice — get sign-off
from your legal counsel.

## Components & licenses

| Component | Where it runs | License | Notes |
|-----------|---------------|---------|-------|
| **Stockfish** (engine binary) | Server (separate process, `/usr/games/stockfish`, invoked via UCI) | **GPL-3.0** | Installed via apt in the backend Docker image. Invoked as a subprocess, **not** statically linked. |
| **python-chess** | Server (Python lib) | **GPL-3.0** | PGN/FEN parsing & validation, UCI engine driver. |
| **react-chessboard** | Browser (frontend) | **MIT** | Board UI. Permissive — no copyleft obligation. |
| **chess.js** | Browser (frontend) | **BSD-2-Clause** | Move legality / SAN / FEN. Permissive. |
| **Stockfish WASM** (optional client engine) | Browser, if you add `public/engine/stockfish.js` | **GPL-3.0** | Not bundled by default; the Analysis page uses the server engine instead. |

## Why the frontend is "clean"
The browser bundle distributed to users contains only **MIT/BSD** code
(react-chessboard, chess.js). No GPL code is shipped to the browser **unless**
you add the optional Stockfish WASM asset — if you do, the GPL applies to what
you distribute to clients, which is a bigger obligation. Default config avoids
this by using the server-side engine.

## The GPL question (server side)
`python-chess` and the Stockfish binary are **GPL-3.0** and run **server-side**:

- They are invoked as a **separate process** (Stockfish) / imported as a library
  (python-chess) on your own servers. You do **not** distribute these binaries to
  end users — users interact over HTTP/MCP.
- The common interpretation: running GPL software on a server to provide a network
  service (SaaS) does **not** by itself trigger the GPL's "distribution" clause
  (this is the well-known "ASP/SaaS loophole"; AGPL would be different —
  neither component is AGPL). So internal/SaaS use is typically fine.
- **However**: if you ever **distribute** the Arkon backend (e.g. ship the Docker
  image or an on-prem appliance to a customer), you are distributing GPL binaries
  and must comply with GPL-3.0 (offer corresponding source, preserve licenses,
  etc.). Arkon is described as "On-Premise" — if you hand the image to customers,
  treat this as distribution and comply.

## Recommended actions before commercial launch
1. **Decide the distribution model**: pure SaaS (you host) vs. on-prem appliance
   shipped to customers. The latter triggers full GPL-3.0 distribution duties.
2. If on-prem/distributed: include GPL-3.0 license texts and a written offer for
   the corresponding source of Stockfish + python-chess (or links to upstream).
3. Keep Stockfish as a **separate process** (already the case) — do not link it
   into a proprietary binary.
4. Do **not** add the Stockfish WASM client asset unless you accept shipping GPL
   to browsers; the server engine already covers analysis.
5. Get **legal sign-off** on the above for your specific go-to-market.

## Fallback if GPL is unacceptable even server-side
Replace the GPL pieces:
- Drop `python-chess` → use a permissive PGN/FEN parser; keep validation on the
  client (chess.js, BSD) and trust-but-verify on the server.
- Drop the server Stockfish → rely solely on the client WASM engine **only if**
  you accept its GPL for browser distribution, or use a permissively-licensed
  engine. (Most strong engines are GPL, so this is the hard part.)

This fallback weakens server-side analysis (the MCP `analyze_position` tool and
async game analysis), so the GPL sign-off path is strongly preferred.
