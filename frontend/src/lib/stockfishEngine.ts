/**
 * Stockfish engine wrapper — runs the engine in a Web Worker and speaks UCI.
 *
 * Phase 1 uses the in-browser single-threaded WASM build so no server CPU and
 * no COOP/COEP headers are required. The engine asset is NOT bundled; drop a
 * Stockfish single-file worker at `public/engine/stockfish.js` (+ its .wasm),
 * or point NEXT_PUBLIC_STOCKFISH_URL at one. If the asset is missing, the
 * engine reports `available = false` and the UI degrades gracefully.
 *
 * Everything here is client-only — import lazily from a "use client" component.
 */

import type { EngineLine } from "@/types/chess";

const ENGINE_URL =
  process.env.NEXT_PUBLIC_STOCKFISH_URL || "/engine/stockfish.js";

type InfoCallback = (line: EngineLine) => void;

function parseInfo(text: string): EngineLine | null {
  if (!text.startsWith("info") || !text.includes(" pv ")) return null;
  const tokens = text.split(/\s+/);
  let depth = 0;
  let scoreCp: number | null = null;
  let mate: number | null = null;
  let pv: string[] = [];
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    if (t === "depth") depth = parseInt(tokens[i + 1], 10) || 0;
    else if (t === "score") {
      const kind = tokens[i + 1];
      const val = parseInt(tokens[i + 2], 10);
      if (kind === "cp") scoreCp = val;
      else if (kind === "mate") mate = val;
    } else if (t === "pv") {
      pv = tokens.slice(i + 1);
      break;
    }
  }
  return { depth, scoreCp, mate, pv };
}

class StockfishEngine {
  private worker: Worker | null = null;
  private ready = false;
  private booting: Promise<boolean> | null = null;
  private current: { onInfo?: InfoCallback; resolve: (l: EngineLine | null) => void } | null = null;
  private best: EngineLine | null = null;

  /** Lazily create the worker and complete the UCI handshake. */
  async init(): Promise<boolean> {
    if (this.ready) return true;
    if (this.booting) return this.booting;
    this.booting = new Promise<boolean>((resolve) => {
      try {
        this.worker = new Worker(ENGINE_URL);
      } catch {
        resolve(false);
        return;
      }
      const onMsg = (e: MessageEvent) => {
        const line = typeof e.data === "string" ? e.data : String(e.data);
        if (line.includes("uciok")) {
          this.post("isready");
        } else if (line.includes("readyok")) {
          this.ready = true;
          this.worker?.removeEventListener("message", onMsg);
          this.worker?.addEventListener("message", this.handleMessage);
          resolve(true);
        }
      };
      this.worker.addEventListener("message", onMsg);
      this.worker.addEventListener("error", () => resolve(false));
      this.post("uci");
    });
    return this.booting;
  }

  private handleMessage = (e: MessageEvent) => {
    const line = typeof e.data === "string" ? e.data : String(e.data);
    if (line.startsWith("info")) {
      const info = parseInfo(line);
      if (info && info.pv.length) {
        this.best = info;
        this.current?.onInfo?.(info);
      }
    } else if (line.startsWith("bestmove")) {
      const done = this.current;
      this.current = null;
      done?.resolve(this.best);
    }
  };

  private post(cmd: string) {
    this.worker?.postMessage(cmd);
  }

  get available() {
    return this.ready;
  }

  /**
   * Analyze a FEN to the given depth. `onInfo` streams progressive lines;
   * the promise resolves with the final best line (or null if unavailable).
   */
  async analyze(
    fen: string,
    opts: { depth?: number; onInfo?: InfoCallback } = {},
  ): Promise<EngineLine | null> {
    const ok = await this.init();
    if (!ok || !this.worker) return null;
    // Cancel any in-flight search.
    if (this.current) {
      this.post("stop");
      this.current.resolve(this.best);
      this.current = null;
    }
    this.best = null;
    const depth = opts.depth ?? 16;
    return new Promise<EngineLine | null>((resolve) => {
      this.current = { onInfo: opts.onInfo, resolve };
      this.post("ucinewgame");
      this.post(`position fen ${fen}`);
      this.post(`go depth ${depth}`);
    });
  }

  stop() {
    if (this.worker) this.post("stop");
  }

  dispose() {
    this.worker?.terminate();
    this.worker = null;
    this.ready = false;
    this.booting = null;
    this.current = null;
  }
}

let singleton: StockfishEngine | null = null;

/** Shared engine instance (one worker per tab). */
export function getEngine(): StockfishEngine {
  if (!singleton) singleton = new StockfishEngine();
  return singleton;
}
