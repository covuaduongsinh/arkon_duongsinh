"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { t } from "@/lib/i18n";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/shared/empty-state";
import { PuzzleTrainer } from "@/components/chess/PuzzleTrainer";
import type { ChessPuzzle, PuzzleStats } from "@/types/chess";

export default function ChessPuzzleTrainPage() {
  const [puzzle, setPuzzle] = useState<ChessPuzzle | null>(null);
  const [stats, setStats] = useState<PuzzleStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [done, setDone] = useState(false);

  const loadNext = useCallback(async () => {
    setLoading(true);
    setDone(false);
    try {
      const res = await api<{ puzzle: ChessPuzzle | null }>("/api/chess/puzzles/next");
      if (res.puzzle) setPuzzle(res.puzzle);
      else {
        setPuzzle(null);
        setDone(true);
      }
    } catch {
      setPuzzle(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadStats = useCallback(async () => {
    try {
      setStats(await api<PuzzleStats>("/api/chess/puzzles/stats/me"));
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    loadNext();
    loadStats();
  }, [loadNext, loadStats]);

  function handleNext() {
    loadStats();
    loadNext();
  }

  return (
    <>
      <PageHeader
        title="Luyện tập"
        description={
          stats
            ? `Elo ${stats.rating ?? 1200} · ${stats.solved} ${t("solved")} · ${Math.round(stats.accuracy * 100)}% ${t("accuracy")}`
            : t("Tactics training")
        }
      />

      {loading ? (
        <p className="text-sm text-muted-foreground">{t("Loading puzzle…")}</p>
      ) : !puzzle ? (
        <EmptyState
          icon="extension"
          title={done ? t("All caught up!") : t("No puzzles available")}
          description={
            done
              ? "Bạn đã giải hết bài tập đã xuất bản trong phạm vi của mình. Quay lại sau nhé."
              : "Chưa có bài tập nào được xuất bản. Hãy nhờ HLV thêm bài."
          }
          action={<Button variant="outline" onClick={loadNext}>Tải lại</Button>}
        />
      ) : (
        <PuzzleTrainer puzzle={puzzle} onNext={handleNext} />
      )}

      <Link href="/chess/puzzles" className="text-sm text-muted-foreground hover:text-foreground">
        ← Thư viện bài tập
      </Link>
    </>
  );
}
