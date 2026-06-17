"use client";

/**
 * Chess board — thin wrapper around react-chessboard (v5, MIT) for a polished
 * look (SVG pieces) and real drag-and-drop, with chess.js as the rules engine.
 *
 * The public prop contract is unchanged from the previous hand-rolled board, so
 * all consumers (PgnViewer, AnalysisPanel, PuzzleTrainer, wiki-content, and the
 * games/play/positions/study pages) keep working without edits:
 *   { fen, orientation?, interactive?, onMove?(BoardMove), lastMove?, className? }
 *
 * Supports both drag-and-drop and click-to-move (tap source then target), legal
 * move dots, last-move highlight, and an inline promotion picker. Colors follow
 * the warm "Sahara" theme.
 */

import { Chess, type Square } from "chess.js";
import { useId, useMemo, useState } from "react";
import { Chessboard, type ChessboardOptions } from "react-chessboard";
import { cn } from "@/lib/utils";

const LIGHT = "#f1e4cf";
const DARK = "#c08552";
const PRIMARY = "#c2652a";

const GLYPH: Record<string, string> = { q: "♛", r: "♜", b: "♝", n: "♞" };

export type BoardMove = {
  from: string;
  to: string;
  promotion?: string;
  san: string;
  fen: string;
};

type Props = {
  fen: string;
  orientation?: "white" | "black";
  interactive?: boolean;
  onMove?: (move: BoardMove) => void;
  lastMove?: { from: string; to: string } | null;
  className?: string;
};

export function ChessBoard({
  fen,
  orientation = "white",
  interactive = false,
  onMove,
  lastMove,
  className,
}: Props) {
  const id = useId();
  const [selected, setSelected] = useState<Square | null>(null);
  const [pendingPromotion, setPendingPromotion] = useState<{ from: Square; to: Square } | null>(null);

  const game = useMemo(() => {
    try {
      return new Chess(fen);
    } catch {
      return null;
    }
  }, [fen]);

  const legalTargets = useMemo(() => {
    if (!game || !selected) return new Map<string, boolean>(); // square -> isCapture
    try {
      const m = new Map<string, boolean>();
      for (const mv of game.moves({ square: selected, verbose: true })) {
        m.set(mv.to as string, !!mv.captured);
      }
      return m;
    } catch {
      return new Map<string, boolean>();
    }
  }, [game, selected]);

  function attempt(from: Square, to: Square, promotion?: string): boolean {
    if (!game) return false;
    const piece = game.get(from);
    const lastRank = to[1] === "8" || to[1] === "1";
    if (piece?.type === "p" && lastRank && !promotion) {
      setPendingPromotion({ from, to });
      return false; // wait for the picker; piece snaps back
    }
    const probe = new Chess(game.fen());
    try {
      const mv = probe.move({ from, to, promotion });
      if (!mv) return false;
      onMove?.({ from, to, promotion, san: mv.san, fen: probe.fen() });
      setSelected(null);
      setPendingPromotion(null);
      return true;
    } catch {
      return false;
    }
  }

  const squareStyles = useMemo(() => {
    const styles: Record<string, React.CSSProperties> = {};
    if (lastMove) {
      styles[lastMove.from] = { backgroundColor: "rgba(194,101,42,0.30)" };
      styles[lastMove.to] = { backgroundColor: "rgba(194,101,42,0.30)" };
    }
    if (selected) {
      styles[selected] = { backgroundColor: "rgba(194,101,42,0.42)" };
    }
    for (const [sq, isCapture] of legalTargets) {
      styles[sq] = isCapture
        ? { boxShadow: `inset 0 0 0 4px rgba(194,101,42,0.55)`, borderRadius: "50%" }
        : { background: "radial-gradient(circle, rgba(58,48,42,0.25) 19%, transparent 21%)" };
    }
    return styles;
  }, [lastMove, selected, legalTargets]);

  const options: ChessboardOptions = {
    id,
    position: fen,
    boardOrientation: orientation,
    allowDragging: interactive,
    showNotation: true,
    animationDurationInMs: 200,
    darkSquareStyle: { backgroundColor: DARK },
    lightSquareStyle: { backgroundColor: LIGHT },
    squareStyles,
    onPieceDrop: ({ sourceSquare, targetSquare }) => {
      if (!interactive || !targetSquare) return false;
      return attempt(sourceSquare as Square, targetSquare as Square);
    },
    onSquareClick: ({ square }) => {
      if (!interactive || !game) return;
      const sq = square as Square;
      if (selected) {
        if (sq === selected) {
          setSelected(null);
          return;
        }
        if (legalTargets.has(sq)) {
          attempt(selected, sq);
          return;
        }
      }
      const piece = game.get(sq);
      if (piece && piece.color === game.turn()) setSelected(sq);
      else setSelected(null);
    },
  };

  if (!game) {
    return (
      <div className={cn("aspect-square w-full max-w-[560px] grid place-items-center rounded-lg border border-black/10 bg-muted text-sm text-muted-foreground", className)}>
        Invalid position
      </div>
    );
  }

  return (
    <div className={cn("relative w-full max-w-[560px]", className)}>
      <div className="overflow-hidden rounded-lg border border-black/10 shadow-sm">
        <Chessboard options={options} />
      </div>

      {pendingPromotion && (
        <div className="absolute inset-0 z-20 grid place-items-center rounded-lg bg-black/40">
          <div className="flex gap-2 rounded-lg bg-background p-3 shadow-lg">
            {(["q", "r", "b", "n"] as const).map((p) => (
              <button
                key={p}
                onClick={() => attempt(pendingPromotion.from, pendingPromotion.to, p)}
                className="grid h-12 w-12 place-items-center rounded-md border border-black/10 text-3xl hover:bg-muted"
                style={{ color: "#262421" }}
                aria-label={`Promote to ${p}`}
              >
                {GLYPH[p]}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
