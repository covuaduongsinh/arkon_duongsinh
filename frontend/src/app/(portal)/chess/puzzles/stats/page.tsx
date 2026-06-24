"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/shared/page-header";
import type { PuzzleStats } from "@/types/chess";

export default function ChessPuzzleStatsPage() {
  const [stats, setStats] = useState<PuzzleStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<PuzzleStats>("/api/chess/puzzles/stats/me")
      .then(setStats)
      .catch(() => setStats(null))
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      <PageHeader title="Puzzle progress" description="Your tactics training stats." />

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <div className="grid grid-cols-2 gap-4 max-w-md sm:grid-cols-4">
          {[
            { label: "Elo", value: stats?.rating ?? 1200 },
            { label: "Đã giải", value: stats?.solved ?? 0 },
            { label: "Lượt thử", value: stats?.attempts ?? 0 },
            { label: "Chính xác", value: `${Math.round((stats?.accuracy ?? 0) * 100)}%` },
          ].map((m) => (
            <div key={m.label} className="rounded-lg border border-black/10 bg-card p-5 text-center">
              <div className="text-3xl font-semibold tabular-nums">{m.value}</div>
              <div className="mt-1 text-sm text-muted-foreground">{m.label}</div>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-3">
        <Link href="/chess/puzzles/train" className="text-sm text-primary hover:underline">Luyện tập →</Link>
        <Link href="/chess" className="text-sm text-muted-foreground hover:text-foreground">← Back to Chess</Link>
      </div>
    </>
  );
}
