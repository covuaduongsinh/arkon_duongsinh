"use client";

/**
 * PGN viewer: parses a PGN with chess.js, renders the board at the current ply
 * and a clickable move list with first/prev/next/last + flip controls.
 */

import { Chess } from "chess.js";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ChessBoard } from "./ChessBoard";

const DEFAULT_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

type ParsedGame = {
  sans: string[];
  fens: string[]; // fens[0] = start, fens[i] = after move i
  lastMoves: ({ from: string; to: string } | null)[];
  error?: string;
};

function parseGame(pgn: string): ParsedGame {
  try {
    const parser = new Chess();
    parser.loadPgn(pgn);
    const moves = parser.history({ verbose: true });
    const startFen =
      moves.length && (moves[0] as { before?: string }).before
        ? (moves[0] as { before?: string }).before!
        : DEFAULT_FEN;
    const replay = new Chess(startFen);
    const fens: string[] = [startFen];
    const lastMoves: ({ from: string; to: string } | null)[] = [null];
    const sans: string[] = [];
    for (const m of moves) {
      replay.move({ from: m.from, to: m.to, promotion: m.promotion });
      fens.push(replay.fen());
      lastMoves.push({ from: m.from, to: m.to });
      sans.push(m.san);
    }
    return { sans, fens, lastMoves };
  } catch (e) {
    return { sans: [], fens: [DEFAULT_FEN], lastMoves: [null], error: String(e) };
  }
}

export function PgnViewer({ pgn, className }: { pgn: string; className?: string }) {
  const parsed = useMemo(() => parseGame(pgn), [pgn]);
  const [ply, setPly] = useState(0); // 0 = start, N = after move N
  const [orientation, setOrientation] = useState<"white" | "black">("white");

  const maxPly = parsed.fens.length - 1;
  const clampedPly = Math.min(ply, maxPly);

  return (
    <div className={cn("flex flex-col gap-4 md:flex-row", className)}>
      <div className="flex-1">
        <ChessBoard
          fen={parsed.fens[clampedPly]}
          orientation={orientation}
          lastMove={parsed.lastMoves[clampedPly]}
        />
        <div className="mt-3 flex items-center gap-1">
          <Button variant="outline" size="sm" onClick={() => setPly(0)} disabled={clampedPly === 0}>
            <span className="material-symbols-outlined text-[18px]">first_page</span>
          </Button>
          <Button variant="outline" size="sm" onClick={() => setPly((p) => Math.max(0, p - 1))} disabled={clampedPly === 0}>
            <span className="material-symbols-outlined text-[18px]">chevron_left</span>
          </Button>
          <Button variant="outline" size="sm" onClick={() => setPly((p) => Math.min(maxPly, p + 1))} disabled={clampedPly === maxPly}>
            <span className="material-symbols-outlined text-[18px]">chevron_right</span>
          </Button>
          <Button variant="outline" size="sm" onClick={() => setPly(maxPly)} disabled={clampedPly === maxPly}>
            <span className="material-symbols-outlined text-[18px]">last_page</span>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto"
            onClick={() => setOrientation((o) => (o === "white" ? "black" : "white"))}
          >
            <span className="material-symbols-outlined text-[18px]">cached</span>
            Flip
          </Button>
        </div>
      </div>

      <div className="w-full md:w-64 shrink-0">
        {parsed.error ? (
          <p className="text-sm text-destructive">Could not parse PGN.</p>
        ) : (
          <div className="rounded-md border border-black/10 bg-card max-h-[420px] overflow-y-auto p-2 text-sm">
            {parsed.sans.length === 0 && (
              <p className="text-muted-foreground p-2">No moves.</p>
            )}
            <div className="grid grid-cols-[auto_1fr_1fr] gap-x-2 gap-y-0.5">
              {Array.from({ length: Math.ceil(parsed.sans.length / 2) }).map((_, i) => {
                const whiteIdx = i * 2;
                const blackIdx = i * 2 + 1;
                return (
                  <div key={i} className="contents">
                    <span className="text-muted-foreground/70 tabular-nums py-0.5">{i + 1}.</span>
                    <button
                      className={cn(
                        "text-left rounded px-1 py-0.5 hover:bg-muted",
                        clampedPly === whiteIdx + 1 && "bg-primary/10 font-semibold",
                      )}
                      onClick={() => setPly(whiteIdx + 1)}
                    >
                      {parsed.sans[whiteIdx]}
                    </button>
                    {parsed.sans[blackIdx] ? (
                      <button
                        className={cn(
                          "text-left rounded px-1 py-0.5 hover:bg-muted",
                          clampedPly === blackIdx + 1 && "bg-primary/10 font-semibold",
                        )}
                        onClick={() => setPly(blackIdx + 1)}
                      >
                        {parsed.sans[blackIdx]}
                      </button>
                    ) : (
                      <span />
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
