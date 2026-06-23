"use client";

import React from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { WikiPageSummary, WikiPageDetail } from "@/types/wiki";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called with a Markdown snippet to splice into the lesson content. */
  onInsert: (markdown: string) => void;
};

function wikiHref(p: { slug: string; scope_type?: string; scope_id?: string | null }): string {
  return p.scope_type && p.scope_type !== "global" && p.scope_id
    ? `/wiki/${p.slug}?scopeType=${p.scope_type}&scopeId=${p.scope_id}`
    : `/wiki/${p.slug}`;
}

/**
 * Lets a teacher pull existing chess wiki knowledge into a lesson. Two modes:
 *  - "Chèn liên kết" inserts a Markdown link to the wiki page (stays in sync).
 *  - "Chèn nội dung" inserts a snapshot of the page's Markdown (editable copy).
 * Reuses the same chess-family wiki list that powers the Chess Wiki landing.
 */
export function WikiInsertPicker({ open, onOpenChange, onInsert }: Props) {
  const [pages, setPages] = React.useState<WikiPageSummary[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [selected, setSelected] = React.useState<WikiPageSummary | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError(null);
    setSelected(null);
    setQuery("");
    api<WikiPageSummary[]>("/api/wiki/pages?knowledge_family=chess&limit=500")
      .then((rows) => setPages(Array.isArray(rows) ? rows : []))
      .catch(() => setPages([]))
      .finally(() => setLoading(false));
  }, [open]);

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return pages;
    return pages.filter(
      (p) => p.title.toLowerCase().includes(q) || p.slug.toLowerCase().includes(q),
    );
  }, [pages, query]);

  function insertLink() {
    if (!selected) return;
    onInsert(`\n[${selected.title}](${wikiHref(selected)})\n`);
    onOpenChange(false);
  }

  async function insertContent() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const qs =
        selected.scope_type && selected.scope_type !== "global" && selected.scope_id
          ? `?scope_type=${selected.scope_type}&scope_id=${selected.scope_id}`
          : "";
      const detail = await api<WikiPageDetail>(`/api/wiki/pages/${selected.slug}${qs}`);
      const body = (detail.content_md || "").trim();
      onInsert(`\n## ${selected.title}\n\n${body}\n`);
      onOpenChange(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Không tải được nội dung trang.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>Chèn từ Wiki Cờ vua</DialogTitle>
          <DialogDescription>
            Chọn một trang kiến thức để chèn liên kết hoặc sao chép nội dung vào bài giảng.
          </DialogDescription>
        </DialogHeader>

        <div className="relative">
          <span className="material-symbols-outlined text-sm text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2">
            search
          </span>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Tìm trang wiki cờ vua…"
            className="h-9 w-full pl-9 pr-3 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
        </div>

        <div className="flex-1 overflow-y-auto rounded-md border border-border min-h-[160px]">
          {loading ? (
            <div className="flex items-center justify-center py-10">
              <span className="material-symbols-outlined text-2xl text-muted-foreground animate-spin">
                progress_activity
              </span>
            </div>
          ) : filtered.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground">Không có trang phù hợp.</p>
          ) : (
            <ul className="divide-y divide-black/[0.06]">
              {filtered.map((p) => (
                <li key={`${p.slug}-${p.scope_id ?? "g"}`}>
                  <button
                    type="button"
                    onClick={() => setSelected(p)}
                    className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                      selected?.slug === p.slug && selected?.scope_id === p.scope_id
                        ? "bg-primary/[0.06] text-primary"
                        : "hover:bg-muted/50"
                    }`}
                  >
                    <span className="font-medium">{p.title}</span>
                    {p.summary && (
                      <span className="block text-xs text-muted-foreground line-clamp-1">
                        {p.summary}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Huỷ
          </Button>
          <Button variant="outline" onClick={insertLink} disabled={!selected || busy} className="gap-1.5">
            <span className="material-symbols-outlined text-sm">link</span>
            Chèn liên kết
          </Button>
          <Button onClick={insertContent} disabled={!selected || busy} className="gap-1.5">
            {busy ? (
              <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
            ) : (
              <span className="material-symbols-outlined text-sm">content_paste</span>
            )}
            Chèn nội dung
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
