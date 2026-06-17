"use client";

/**
 * Puzzle trainer — supports multi-move tactics. The solver plays a move; the
 * server validates it against the (hidden) solution and returns the opponent's
 * auto-reply, which is played on the board so the solver continues. Solving or
 * a wrong move ends the puzzle and reveals the full line for review.
 */

import { Chess } from "chess.js";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { t } from "@/lib/i18n";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ChessPuzzle, PuzzleAttemptResult } from "@/types/chess";
import { ChessBoard, type BoardMove } from "./ChessBoard";
import { PgnViewer } from "./PgnViewer";

type Status = "thinking" | "correct" | "wrong";
type StepResult = {
  correct: boolean;
  solved: boolean;
  reply_uci: string | null;
  solution_moves?: string[];
};

function playUci(fen: string, uci: string): string | null {
  try {
    const c = new Chess(fen);
    const mv = c.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci.length > 4 ? uci[4] : undefined });
    return mv ? c.fen() : null;
  } catch {
    return null;
  }
}

export function PuzzleTrainer({
  puzzle,
  onNext,
}: {
  puzzle: ChessPuzzle;
  onNext?: () => void;
}) {
  const [status, setStatus] = useState<Status>("thinking");
  const [boardFen, setBoardFen] = useState(puzzle.fen);
  const [played, setPlayed] = useState<string[]>([]);
  const [lastMove, setLastMove] = useState<{ from: string; to: string } | null>(null);
  const [solution, setSolution] = useState<string[] | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [start] = useState(() => Date.now());

  // Reset when the puzzle changes.
  useEffect(() => {
    setStatus("thinking");
    setBoardFen(puzzle.fen);
    setPlayed([]);
    setLastMove(null);
    setSolution(null);
  }, [puzzle.id, puzzle.fen]);

  const orientation = puzzle.side_to_move === "w" ? "white" : "black";

  async function onMove(m: BoardMove) {
    if (status !== "thinking" || submitting) return;
    const uci = `${m.from}${m.to}${m.promotion ?? ""}`;
    const newPlayed = [...played, uci];
    setBoardFen(m.fen);
    setLastMove({ from: m.from, to: m.to });
    setPlayed(newPlayed);
    setSubmitting(true);
    try {
      const res = await api<StepResult>(`/api/chess/puzzles/${puzzle.id}/step`, {
        method: "POST",
        body: { moves: newPlayed, time_ms: Date.now() - start },
      });
      if (!res.correct) {
        setSolution(res.solution_moves ?? null);
        setStatus("wrong");
        return;
      }
      if (res.solved) {
        setSolution(res.solution_moves ?? null);
        setStatus("correct");
        return;
      }
      if (res.reply_uci) {
        const replyFen = playUci(m.fen, res.reply_uci);
        if (replyFen) {
          setBoardFen(replyFen);
          setPlayed([...newPlayed, res.reply_uci]);
          setLastMove({ from: res.reply_uci.slice(0, 2), to: res.reply_uci.slice(2, 4) });
        }
      }
    } catch {
      setStatus("wrong");
    } finally {
      setSubmitting(false);
    }
  }

  const solutionPgn = useMemo(() => {
    if (!solution) return null;
    try {
      return buildSolutionPgn(puzzle.fen, solution);
    } catch {
      return null;
    }
  }, [solution, puzzle.fen]);

  return (
    <div className="flex flex-col gap-4 lg:flex-row">
      <div className="flex-1">
        {status !== "thinking" && solutionPgn ? (
          <PgnViewer pgn={solutionPgn} />
        ) : (
          <ChessBoard
            fen={boardFen}
            orientation={orientation}
            interactive={status === "thinking" && !submitting}
            onMove={onMove}
            lastMove={lastMove}
          />
        )}
      </div>

      <div className="w-full lg:w-72 shrink-0 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-heading text-lg">{puzzle.title || t("Find the best move")}</h3>
          {puzzle.rating != null && <Badge variant="secondary">{puzzle.rating}</Badge>}
        </div>
        <p className="text-sm text-muted-foreground">
          {puzzle.side_to_move === "w" ? t("White to move.") : t("Black to move.")}
          {puzzle.description ? ` ${puzzle.description}` : ""}
        </p>
        {puzzle.themes?.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {puzzle.themes.map((th) => (
              <Badge key={th} variant="outline" className="text-xs">{th}</Badge>
            ))}
          </div>
        )}

        {status === "correct" && (
          <div className="rounded-md bg-green-600/10 p-3 text-sm text-green-700">
            <span className="material-symbols-outlined align-middle text-[18px]">check_circle</span>{" "}
            {t("Correct! Replay the full line on the board.")}
          </div>
        )}
        {status === "wrong" && (
          <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
            <span className="material-symbols-outlined align-middle text-[18px]">cancel</span>{" "}
            {t("Not the best move — see the solution on the board.")}
          </div>
        )}

        <div className="flex gap-2">
          {status === "thinking" ? (
            <Button
              variant="outline"
              onClick={async () => {
                // Give up — reveal via the attempt endpoint (records a failed attempt).
                try {
                  const res = await api<PuzzleAttemptResult>(
                    `/api/chess/puzzles/${puzzle.id}/attempt`,
                    { method: "POST", body: { moves_played: [] } },
                  );
                  setSolution(res.solution_moves);
                  setStatus("wrong");
                } catch {
                  /* ignore */
                }
              }}
            >
              {t("Show solution")}
            </Button>
          ) : (
            onNext && (
              <Button onClick={onNext}>
                {t("Next puzzle")}
                <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
              </Button>
            )
          )}
        </div>
      </div>
    </div>
  );
}

/** Construct a `[FEN ...]`-seeded PGN from a UCI solution line using chess.js. */
function buildSolutionPgn(fen: string, uciMoves: string[]): string {
  const c = new Chess(fen);
  for (const uci of uciMoves) {
    try {
      c.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci.length > 4 ? uci[4] : undefined });
    } catch {
      break;
    }
  }
  return c.pgn();
}
