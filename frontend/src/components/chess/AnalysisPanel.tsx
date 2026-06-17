"use client";

/**
 * Free-play analysis board with the in-browser Stockfish engine. Play moves on
 * the board and the engine re-analyzes the current position, streaming the
 * eval and best line. Degrades gracefully when the engine asset is missing.
 */

import { Chess } from "chess.js";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { getEngine } from "@/lib/stockfishEngine";
import type { EngineLine } from "@/types/chess";
import { ChessBoard, type BoardMove } from "./ChessBoard";
import { EvalBar } from "./EvalBar";

const DEFAULT_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

/** Convert a UCI PV to SAN for readable display (best-effort). */
function pvToSan(fen: string, pv: string[]): string[] {
  try {
    const c = new Chess(fen);
    const out: string[] = [];
    for (const uci of pv.slice(0, 8)) {
      const from = uci.slice(0, 2);
      const to = uci.slice(2, 4);
      const promotion = uci.length > 4 ? uci[4] : undefined;
      const mv = c.move({ from, to, promotion });
      if (!mv) break;
      out.push(mv.san);
    }
    return out;
  } catch {
    return [];
  }
}

export function AnalysisPanel({ initialFen = DEFAULT_FEN }: { initialFen?: string }) {
  const [fen, setFen] = useState(initialFen);
  const [lastMove, setLastMove] = useState<{ from: string; to: string } | null>(null);
  const [history, setHistory] = useState<string[]>([]);
  const [orientation, setOrientation] = useState<"white" | "black">("white");
  const [line, setLine] = useState<EngineLine | null>(null);
  const [depth, setDepth] = useState(16);
  const [engineState, setEngineState] = useState<"idle" | "loading" | "ready" | "server" | "unavailable">("idle");
  const reqId = useRef(0);

  useEffect(() => {
    setFen(initialFen);
    setHistory([]);
    setLastMove(null);
  }, [initialFen]);

  const analyze = useCallback(
    async (targetFen: string) => {
      const engine = getEngine();
      setEngineState((s) => (s === "ready" ? s : "loading"));
      const myReq = ++reqId.current;
      const ok = await engine.init();
      if (ok) {
        setEngineState("ready");
        setLine(null);
        const final = await engine.analyze(targetFen, {
          depth,
          onInfo: (info) => {
            if (myReq === reqId.current) setLine(info);
          },
        });
        if (myReq === reqId.current && final) setLine(final);
        return;
      }
      // No in-browser WASM engine — fall back to the server-side Stockfish.
      setEngineState("server");
      setLine(null);
      try {
        const r = await api<{ eval_cp: number | null; mate: number | null; best_move: string | null; pv: string[]; depth: number }>(
          "/api/chess/analysis",
          { method: "POST", body: { fen: targetFen, depth } },
        );
        if (myReq === reqId.current) {
          // Server returns White-POV; store as side-to-move POV like the WASM path.
          const stm = (() => {
            try {
              return new Chess(targetFen).turn();
            } catch {
              return "w" as const;
            }
          })();
          const sign = stm === "w" ? 1 : -1;
          setLine({
            depth: r.depth,
            scoreCp: r.eval_cp == null ? null : r.eval_cp * sign,
            mate: r.mate == null ? null : r.mate * sign,
            pv: r.pv || [],
          });
        }
      } catch {
        if (myReq === reqId.current) setEngineState("unavailable");
      }
    },
    [depth],
  );

  useEffect(() => {
    analyze(fen);
    return () => {
      getEngine().stop();
    };
  }, [fen, analyze]);

  function onMove(m: BoardMove) {
    setHistory((h) => [...h, fen]);
    setFen(m.fen);
    setLastMove({ from: m.from, to: m.to });
  }

  function undo() {
    setHistory((h) => {
      if (!h.length) return h;
      const prev = h[h.length - 1];
      setFen(prev);
      setLastMove(null);
      return h.slice(0, -1);
    });
  }

  function reset() {
    setHistory([]);
    setFen(initialFen);
    setLastMove(null);
  }

  // Engine score is from side-to-move POV; convert to White POV for the bar.
  const turn = (() => {
    try {
      return new Chess(fen).turn();
    } catch {
      return "w" as const;
    }
  })();
  const whiteCp = line?.scoreCp != null ? (turn === "w" ? line.scoreCp : -line.scoreCp) : null;
  const whiteMate = line?.mate != null ? (turn === "w" ? line.mate : -line.mate) : null;
  const pvSan = line ? pvToSan(fen, line.pv) : [];

  return (
    <div className="flex flex-col gap-4 lg:flex-row">
      <div className="flex gap-2">
        <div className="h-[min(560px,90vw)]">
          <EvalBar scoreCp={whiteCp} mate={whiteMate} />
        </div>
        <ChessBoard fen={fen} orientation={orientation} interactive onMove={onMove} lastMove={lastMove} />
      </div>

      <div className="flex-1 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={undo} disabled={!history.length}>
            <span className="material-symbols-outlined text-[18px]">undo</span>
            Undo
          </Button>
          <Button variant="outline" size="sm" onClick={reset}>
            Reset
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setOrientation((o) => (o === "white" ? "black" : "white"))}>
            <span className="material-symbols-outlined text-[18px]">cached</span>
            Flip
          </Button>
          <label className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
            Depth
            <input
              type="range"
              min={8}
              max={22}
              value={depth}
              onChange={(e) => setDepth(Number(e.target.value))}
              className="accent-primary"
            />
            <span className="tabular-nums w-6">{depth}</span>
          </label>
        </div>

        <div className="rounded-md border border-black/10 bg-card p-3 text-sm">
          {engineState === "unavailable" ? (
            <p className="text-muted-foreground">
              Engine not loaded. Add a Stockfish build to{" "}
              <code className="text-xs">public/engine/stockfish.js</code> to enable analysis.
            </p>
          ) : engineState === "loading" ? (
            <p className="text-muted-foreground">Loading engine…</p>
          ) : line ? (
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="font-semibold tabular-nums">
                  {whiteMate != null
                    ? `Mate in ${Math.abs(whiteMate)}`
                    : `${whiteCp != null && whiteCp >= 0 ? "+" : ""}${((whiteCp ?? 0) / 100).toFixed(2)}`}
                </span>
                <span className="text-xs text-muted-foreground">depth {line.depth}{engineState === "server" ? " · server" : ""}</span>
              </div>
              <p className="text-muted-foreground leading-relaxed">{pvSan.join(" ")}</p>
            </div>
          ) : (
            <p className="text-muted-foreground">Analyzing…</p>
          )}
        </div>

        <p className="break-all rounded-md bg-muted/50 p-2 font-mono text-[11px] text-muted-foreground">{fen}</p>
      </div>
    </div>
  );
}
