"use client";

import React from "react";
import Link from "next/link";
import { api } from "@/lib/api";

// Phase 2 — "Nội dung cờ vua liên quan" block on a wiki page.
// Backed by GET /api/wiki/chess-links/{slug}: study sets / lessons whose
// companion wiki_slug is this page, plus chess Sources that fed it.

type ChessLinks = {
  study_sets: { id: string; title: string; kind: string }[];
  lessons: { id: string; title: string; class_id: string }[];
  sources: { id: string; title: string; source_type: string }[];
};

export function WikiChessLinks({ slug, linkSuffix = "" }: { slug: string; linkSuffix?: string }) {
  const [data, setData] = React.useState<ChessLinks | null>(null);

  React.useEffect(() => {
    if (!slug) return;
    let cancelled = false;
    api<ChessLinks>(`/api/wiki/chess-links/${encodeURIComponent(slug)}`)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => {
        if (!cancelled) setData(null);
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  const total =
    (data?.study_sets.length ?? 0) +
    (data?.lessons.length ?? 0) +
    (data?.sources.length ?? 0);
  if (!data || total === 0) return null;

  return (
    <div className="mt-12 pt-8 border-t border-border">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-4 flex items-center gap-1.5">
        <span className="material-symbols-outlined text-sm">chess</span>
        Nội dung cờ vua liên quan ({total})
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {data.lessons.map((l) => (
          <Link
            key={`lesson-${l.id}`}
            href={`/chess/lessons/${l.id}`}
            className="rounded-xl border bg-card p-3 flex items-center gap-3 shadow-sm hover:shadow-md transition-shadow"
          >
            <span className="material-symbols-outlined text-primary">menu_book</span>
            <div className="min-w-0">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Bài giảng</div>
              <div className="text-sm font-medium text-foreground truncate">{l.title}</div>
            </div>
          </Link>
        ))}
        {data.study_sets.map((s) => (
          <Link
            key={`study-${s.id}`}
            href={`/chess/study/${s.id}`}
            className="rounded-xl border bg-card p-3 flex items-center gap-3 shadow-sm hover:shadow-md transition-shadow"
          >
            <span className="material-symbols-outlined text-primary">library_books</span>
            <div className="min-w-0">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Bộ học liệu · {s.kind}</div>
              <div className="text-sm font-medium text-foreground truncate">{s.title}</div>
            </div>
          </Link>
        ))}
        {data.sources.map((src) => (
          <Link
            key={`source-${src.id}`}
            href={`/wiki/source/${src.id}${linkSuffix}`}
            className="rounded-xl border bg-card p-3 flex items-center gap-3 shadow-sm hover:shadow-md transition-shadow"
          >
            <span className="material-symbols-outlined text-primary">description</span>
            <div className="min-w-0">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Nguồn cờ vua</div>
              <div className="text-sm font-medium text-foreground truncate">{src.title}</div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
