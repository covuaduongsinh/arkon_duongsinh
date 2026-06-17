"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { t } from "@/lib/i18n";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/empty-state";
import type { ChessMatch } from "@/types/chess";

export default function ChessPlayPage() {
  const router = useRouter();
  const [matches, setMatches] = useState<ChessMatch[]>([]);
  const [openMatches, setOpenMatches] = useState<ChessMatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [color, setColor] = useState<"white" | "black">("white");
  const [level, setLevel] = useState(4);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [mine, open] = await Promise.all([
        api<{ items: ChessMatch[] }>("/api/chess/matches"),
        api<{ items: ChessMatch[] }>("/api/chess/matches/open"),
      ]);
      setMatches(mine.items);
      setOpenMatches(open.items);
    } catch {
      setMatches([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function createChallenge() {
    setCreating(true);
    setError(null);
    try {
      const m = await api<ChessMatch>("/api/chess/matches", {
        method: "POST",
        body: { mode: "human_vs_human", player_color: color },
      });
      router.push(`/chess/play/${m.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Tạo thách đấu thất bại");
      setCreating(false);
    }
  }

  async function joinChallenge(matchId: string) {
    try {
      const m = await api<ChessMatch>(`/api/chess/matches/${matchId}/join`, { method: "POST" });
      router.push(`/chess/play/${m.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Tham gia thất bại");
    }
  }

  async function startVsEngine() {
    setCreating(true);
    setError(null);
    try {
      const m = await api<ChessMatch>("/api/chess/matches", {
        method: "POST",
        body: { mode: "human_vs_engine", player_color: color, engine_level: level },
      });
      router.push(`/chess/play/${m.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to start match");
      setCreating(false);
    }
  }

  return (
    <>
      <PageHeader title={t("Play")} description={t("Play against the engine or a colleague.")} />

      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-black/10 bg-card p-4">
        <div>
          <label className="mb-1 block text-sm font-medium">{t("Your color")}</label>
          <select value={color} onChange={(e) => setColor(e.target.value as "white" | "black")} className="h-9 rounded-md border border-black/10 bg-background px-2 text-sm">
            <option value="white">{t("White")}</option>
            <option value="black">{t("Black")}</option>
          </select>
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">{t("Engine level")}</label>
          <select value={level} onChange={(e) => setLevel(Number(e.target.value))} className="h-9 rounded-md border border-black/10 bg-background px-2 text-sm">
            {[1, 2, 3, 4, 5, 6, 7, 8].map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </div>
        <Button onClick={startVsEngine} disabled={creating}>
          <span className="material-symbols-outlined text-[18px]">smart_toy</span>
          {t("Play vs Engine")}
        </Button>
        <Button variant="outline" onClick={createChallenge} disabled={creating}>
          <span className="material-symbols-outlined text-[18px]">group_add</span>
          Tạo thách đấu (người)
        </Button>
        {error && <p className="w-full text-sm text-destructive">{error}</p>}
      </div>

      {openMatches.length > 0 && (
        <div className="rounded-lg border border-black/10 bg-card p-4">
          <h3 className="mb-2 font-heading text-lg">Thách đấu đang mở</h3>
          <div className="space-y-1.5">
            {openMatches.map((m) => (
              <div key={m.id} className="flex items-center justify-between text-sm">
                <span>Thách đấu · cầm quân {m.white_employee_id ? "Đen" : "Trắng"}</span>
                <Button size="sm" onClick={() => joinChallenge(m.id)}>Tham gia</Button>
              </div>
            ))}
          </div>
        </div>
      )}

      <h3 className="font-heading text-lg">{t("Your matches")}</h3>
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : matches.length === 0 ? (
        <EmptyState icon="swords" title={t("No matches yet")} description={t("Start one above.")} />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-black/10">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-left text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">{t("Mode")}</th>
                <th className="px-3 py-2 font-medium">{t("Your color")}</th>
                <th className="px-3 py-2 font-medium">{t("Status")}</th>
                <th className="px-3 py-2 font-medium">{t("Result")}</th>
                <th className="px-3 py-2 font-medium">{t("Moves")}</th>
              </tr>
            </thead>
            <tbody>
              {matches.map((m) => (
                <tr key={m.id} onClick={() => router.push(`/chess/play/${m.id}`)} className="cursor-pointer border-t border-black/[0.06] hover:bg-muted/30">
                  <td className="px-3 py-2">{m.mode === "human_vs_engine" ? `Engine (lv${m.engine_level})` : "Human"}</td>
                  <td className="px-3 py-2 capitalize">{m.your_color || "—"}</td>
                  <td className="px-3 py-2">
                    <Badge variant={m.status === "active" ? "default" : "secondary"}>{m.status}</Badge>
                  </td>
                  <td className="px-3 py-2 tabular-nums">{m.result || "—"}</td>
                  <td className="px-3 py-2 tabular-nums text-muted-foreground">{Math.ceil(m.moves.length / 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Link href="/chess" className="text-sm text-muted-foreground hover:text-foreground">{t("Back to Chess")}</Link>
    </>
  );
}
