"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { t } from "@/lib/i18n";
import { PageHeader } from "@/components/shared/page-header";
import type { PuzzleStats } from "@/types/chess";

const TILES = [
  { href: "/chess/games", icon: "deployed_code", title: "Games", desc: "Browse and import the game database (PGN)." },
  { href: "/chess/analysis", icon: "neurology", title: "Analysis", desc: "Play out positions with the Stockfish engine." },
  { href: "/chess/puzzles", icon: "extension", title: "Puzzles", desc: "Train tactics and track your progress." },
  { href: "/chess/games/import", icon: "upload_file", title: "Import PGN", desc: "Add games from a .pgn file or pasted text." },
];

export default function ChessHomePage() {
  const [stats, setStats] = useState<PuzzleStats | null>(null);

  useEffect(() => {
    api<PuzzleStats>("/api/chess/puzzles/stats/me").then(setStats).catch(() => setStats(null));
  }, []);

  return (
    <>
      <PageHeader
        title={t("Chess")}
        description={t("Game database, engine analysis, and tactics training for Dương Sinh Chess.")}
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {TILES.map((tile) => (
          <Link
            key={tile.href}
            href={tile.href}
            className="group rounded-lg border border-black/10 bg-card p-5 transition-colors hover:border-primary/40 hover:bg-primary/[0.03]"
          >
            <span className="material-symbols-outlined text-3xl text-primary">{tile.icon}</span>
            <h3 className="mt-3 font-heading text-lg">{t(tile.title)}</h3>
            <p className="mt-1 text-sm text-muted-foreground">{t(tile.desc)}</p>
          </Link>
        ))}
      </div>

      {stats && (
        <div className="rounded-lg border border-black/10 bg-card p-5">
          <h3 className="font-heading text-lg">{t("Your puzzle progress")}</h3>
          <div className="mt-3 flex gap-8 text-sm">
            <div>
              <div className="text-2xl font-semibold tabular-nums">{stats.solved}</div>
              <div className="text-muted-foreground">{t("solved")}</div>
            </div>
            <div>
              <div className="text-2xl font-semibold tabular-nums">{stats.attempts}</div>
              <div className="text-muted-foreground">{t("attempts")}</div>
            </div>
            <div>
              <div className="text-2xl font-semibold tabular-nums">{Math.round(stats.accuracy * 100)}%</div>
              <div className="text-muted-foreground">{t("accuracy")}</div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
