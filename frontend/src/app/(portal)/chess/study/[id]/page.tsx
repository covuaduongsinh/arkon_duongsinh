"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ChessBoard } from "@/components/chess/ChessBoard";

type StudyItem = {
  id: string;
  position: number;
  item_type: "game" | "puzzle" | "fen";
  game_id?: string | null;
  puzzle_id?: string | null;
  fen_id?: string | null;
  note?: string | null;
};

type StudySetDetail = {
  id: string;
  title: string;
  description?: string | null;
  kind: string;
  wiki_slug?: string | null;
  items: StudyItem[];
};

export default function ChessStudyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { hasPermission } = useAuth();
  const canCoach = hasPermission("chess:coach");

  const [study, setStudy] = useState<StudySetDetail | null>(null);
  const [loading, setLoading] = useState(true);
  // Resolved FENs for fen/puzzle items, keyed by item id.
  const [fens, setFens] = useState<Record<string, string>>({});
  const [itemType, setItemType] = useState("fen");
  const [refId, setRefId] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  // Options for the "add item" picker, loaded per item type.
  const [pickerOptions, setPickerOptions] = useState<{ id: string; label: string }[]>([]);
  // Publish-to-wiki (review-gated companion page).
  const [publishing, setPublishing] = useState(false);
  const [publishMsg, setPublishMsg] = useState<string | null>(null);

  // Load selectable items whenever the coach switches the item type.
  useEffect(() => {
    if (!canCoach) return;
    let cancelled = false;
    setRefId("");
    (async () => {
      try {
        if (itemType === "game") {
          const d = await api<{ items: { id: string; white?: string | null; black?: string | null; result?: string | null }[] }>("/api/chess/games?page_size=100");
          if (!cancelled) setPickerOptions(d.items.map((g) => ({ id: g.id, label: `${g.white || "?"} vs ${g.black || "?"} (${g.result || "*"})` })));
        } else if (itemType === "puzzle") {
          const d = await api<{ items: { id: string; title?: string | null; rating?: number | null }[] }>("/api/chess/puzzles?page_size=100");
          if (!cancelled) setPickerOptions(d.items.map((p) => ({ id: p.id, label: `${p.title || "Puzzle"}${p.rating ? ` (${p.rating})` : ""}` })));
        } else {
          const d = await api<{ items: { id: string; label?: string | null; fen: string }[] }>("/api/chess/positions?page_size=100");
          if (!cancelled) setPickerOptions(d.items.map((p) => ({ id: p.id, label: p.label || p.fen })));
        }
      } catch {
        if (!cancelled) setPickerOptions([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [itemType, canCoach]);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const data = await api<StudySetDetail>(`/api/chess/study-sets/${id}`);
      setStudy(data);
      // Resolve boards for fen/puzzle items.
      const resolved: Record<string, string> = {};
      await Promise.all(
        data.items.map(async (it) => {
          try {
            if (it.item_type === "fen" && it.fen_id) {
              const p = await api<{ fen: string }>(`/api/chess/positions/${it.fen_id}`);
              resolved[it.id] = p.fen;
            } else if (it.item_type === "puzzle" && it.puzzle_id) {
              const p = await api<{ fen: string }>(`/api/chess/puzzles/${it.puzzle_id}`);
              resolved[it.id] = p.fen;
            }
          } catch {
            /* skip unresolved */
          }
        }),
      );
      setFens(resolved);
    } catch {
      setStudy(null);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  async function publishWiki() {
    setPublishing(true);
    setPublishMsg(null);
    try {
      const r = await api<{ draft_id: string; slug: string; status: string }>(
        `/api/chess/study-sets/${id}/publish-wiki`,
        { method: "POST" },
      );
      setPublishMsg(`Đã gửi vào hàng đợi Duyệt bài (slug: ${r.slug}). Khi được duyệt, trang wiki sẽ xuất hiện.`);
      await load();
    } catch (e) {
      setPublishMsg(e instanceof ApiError ? e.message : "Không thể xuất bản lên wiki");
    } finally {
      setPublishing(false);
    }
  }

  async function addItem() {
    if (!refId.trim()) return;
    setError(null);
    const body: Record<string, unknown> = { item_type: itemType, note: note || null };
    body[`${itemType === "fen" ? "fen" : itemType}_id`] = refId.trim();
    try {
      await api(`/api/chess/study-sets/${id}/items`, { method: "POST", body });
      setRefId("");
      setNote("");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to add item");
    }
  }

  if (loading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (!study) return <p className="text-sm text-muted-foreground">Study set not found.</p>;

  return (
    <>
      <PageHeader
        title={study.title}
        description={study.description || undefined}
        action={
          <div className="flex items-center gap-2">
            <Badge variant="secondary">{study.kind}</Badge>
            {study.wiki_slug && (
              <Link href={`/wiki/${study.wiki_slug}`} className="text-sm text-primary hover:underline inline-flex items-center gap-1">
                <span className="material-symbols-outlined text-sm">menu_book</span>
                Trang wiki
              </Link>
            )}
            {canCoach && (
              <Button variant="outline" size="sm" onClick={publishWiki} disabled={publishing} className="gap-1.5">
                <span className="material-symbols-outlined text-sm">upload</span>
                {publishing ? "Đang gửi…" : "Xuất bản lên Wiki"}
              </Button>
            )}
          </div>
        }
      />

      {publishMsg && (
        <p className="rounded-md border border-black/10 bg-muted/40 px-3 py-2 text-sm text-muted-foreground">{publishMsg}</p>
      )}

      {canCoach && (
        <div className="flex flex-wrap items-end gap-2 rounded-lg border border-black/10 bg-card p-4">
          <select value={itemType} onChange={(e) => setItemType(e.target.value)} className="h-9 rounded-md border border-black/10 bg-background px-2 text-sm">
            <option value="fen">Position (FEN)</option>
            <option value="game">Game</option>
            <option value="puzzle">Puzzle</option>
          </select>
          <select
            value={refId}
            onChange={(e) => setRefId(e.target.value)}
            className="h-9 min-w-[260px] flex-1 rounded-md border border-black/10 bg-background px-2 text-sm"
          >
            <option value="">
              {pickerOptions.length ? `Select a ${itemType}…` : `No ${itemType}s available`}
            </option>
            {pickerOptions.map((o) => (
              <option key={o.id} value={o.id}>{o.label}</option>
            ))}
          </select>
          <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (optional)" className="min-w-[160px]" />
          <Button onClick={addItem} disabled={!refId.trim()}>Add</Button>
          {error && <p className="w-full text-sm text-destructive">{error}</p>}
        </div>
      )}

      {study.items.length === 0 ? (
        <p className="text-sm text-muted-foreground">No items yet.</p>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {study.items.map((it) => (
            <div key={it.id} className="rounded-lg border border-black/10 bg-card p-3">
              <div className="mb-2 flex items-center justify-between">
                <Badge variant="outline">{it.item_type}</Badge>
                {it.item_type === "game" && it.game_id && (
                  <Link href={`/chess/games/${it.game_id}`} className="text-xs text-primary hover:underline">Open game →</Link>
                )}
              </div>
              {fens[it.id] && <ChessBoard fen={fens[it.id]} className="max-w-[260px]" />}
              {it.note && <p className="mt-2 text-sm text-muted-foreground">{it.note}</p>}
            </div>
          ))}
        </div>
      )}

      <Link href="/chess/study" className="text-sm text-muted-foreground hover:text-foreground">← Back to Study sets</Link>
    </>
  );
}
