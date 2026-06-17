"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { t } from "@/lib/i18n";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { PgnViewer } from "@/components/chess/PgnViewer";
import { EvalGraph } from "@/components/chess/EvalGraph";
import type { ChessGameDetail } from "@/types/chess";

export default function ChessGameDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { hasPermission } = useAuth();
  const canDelete = hasPermission("chess:delete:own_dept") || hasPermission("chess:delete:all");

  const [game, setGame] = useState<ChessGameDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchGame = useCallback(async () => {
    if (!id) return;
    try {
      setGame(await api<ChessGameDetail>(`/api/chess/games/${id}`));
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) setNotFound(true);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchGame();
  }, [fetchGame]);

  // Poll while analysis is in progress.
  const analyzing = game?.analysis_status === "queued" || game?.analysis_status === "running";
  useEffect(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    if (analyzing) pollRef.current = setInterval(fetchGame, 2500);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [analyzing, fetchGame]);

  async function onDelete() {
    if (!game || !confirm("Xoá ván này?")) return;
    await api(`/api/chess/games/${game.id}`, { method: "DELETE" });
    router.push("/chess/games");
  }

  async function analyze() {
    if (!game) return;
    await api(`/api/chess/games/${game.id}/analyze`, { method: "POST" });
    setGame({ ...game, analysis_status: "queued" });
  }

  if (loading) return <p className="text-sm text-muted-foreground">Đang tải…</p>;
  if (notFound || !game) return <p className="text-sm text-muted-foreground">Không tìm thấy ván.</p>;

  const title = `${game.white || "?"} vs ${game.black || "?"}`;
  const a = game.analysis_json;
  const notable = a?.moves.filter((m) => m.class !== "ok") ?? [];

  return (
    <>
      <PageHeader
        title={title}
        description={[game.event, game.played_at, game.eco && `${game.eco} ${game.opening_name || ""}`]
          .filter(Boolean)
          .join(" · ")}
        action={
          <div className="flex items-center gap-2">
            <Badge variant="secondary">{game.result || "*"}</Badge>
            {canDelete && (
              <Button variant="outline" size="sm" onClick={onDelete}>
                <span className="material-symbols-outlined text-[18px]">delete</span>
                {t("Delete")}
              </Button>
            )}
          </div>
        }
      />

      <PgnViewer pgn={game.pgn} />

      {/* Engine game report */}
      <div className="rounded-lg border border-black/10 bg-card p-4">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="font-heading text-lg">Phân tích ván (engine)</h3>
          {game.analysis_status === "none" || game.analysis_status === "error" ? (
            <Button size="sm" onClick={analyze}>
              <span className="material-symbols-outlined text-[18px]">neurology</span>
              Phân tích ván
            </Button>
          ) : analyzing ? (
            <span className="flex items-center gap-1 text-sm text-muted-foreground">
              <span className="material-symbols-outlined animate-spin text-[18px]">progress_activity</span>
              Đang phân tích…
            </span>
          ) : (
            <Button size="sm" variant="outline" onClick={analyze}>Phân tích lại</Button>
          )}
        </div>

        {game.analysis_status === "error" && (
          <p className="text-sm text-destructive">Phân tích thất bại (engine không khả dụng).</p>
        )}

        {a && (
          <div className="space-y-3">
            <EvalGraph evals={a.evals} />
            <div className="flex gap-4 text-sm">
              <span className="text-destructive">● {a.summary.blunder} sai lầm nặng</span>
              <span className="text-amber-600">● {a.summary.mistake} sai lầm</span>
              <span className="text-muted-foreground">● {a.summary.inaccuracy} thiếu chính xác</span>
            </div>
            {notable.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {notable.map((m) => (
                  <Badge
                    key={m.ply}
                    variant="outline"
                    className={
                      m.class === "blunder" ? "border-destructive/40 text-destructive"
                        : m.class === "mistake" ? "border-amber-500/40 text-amber-600"
                          : "text-muted-foreground"
                    }
                  >
                    {Math.ceil(m.ply / 2)}{m.side === "white" ? "." : "…"} {m.san}
                  </Badge>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {game.final_fen && (
        <Link
          href={`/chess/analysis?fen=${encodeURIComponent(game.final_fen)}`}
          className="inline-flex w-fit items-center gap-1 text-sm text-primary hover:underline"
        >
          <span className="material-symbols-outlined text-[18px]">neurology</span>
          {t("Analyze final position")}
        </Link>
      )}

      <Link href="/chess/games" className="text-sm text-muted-foreground hover:text-foreground">
        {t("Back to Games")}
      </Link>
    </>
  );
}
