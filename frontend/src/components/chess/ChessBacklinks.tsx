"use client";

import React from "react";
import Link from "next/link";

import { api } from "@/lib/api";
import type { ChessLinkType } from "@/lib/hooks/use-chess-resolver";

type Backlinks = {
  pages: { slug: string; title: string; scope_type: string; scope_id: string | null }[];
  lessons: { id: string; title: string; class_id: string }[];
};

/**
 * "Wiki / bài giảng nhắc tới" — reverse direction of chess wikilinks. Shows the
 * wiki pages and chess lessons that reference this entity via `[[game:…]]` etc.
 * Rendered on chess game/position/puzzle/study detail pages.
 */
export function ChessBacklinks({
  type,
  id,
  linkSuffix = "",
}: {
  type: ChessLinkType;
  id: string;
  linkSuffix?: string;
}) {
  const [data, setData] = React.useState<Backlinks | null>(null);

  React.useEffect(() => {
    if (!id) return;
    let cancelled = false;
    api<Backlinks>(`/api/chess/backlinks?type=${type}&id=${encodeURIComponent(id)}`)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => {
        if (!cancelled) setData(null);
      });
    return () => {
      cancelled = true;
    };
  }, [type, id]);

  const total = (data?.pages.length ?? 0) + (data?.lessons.length ?? 0);
  if (!data || total === 0) return null;

  return (
    <div className="mt-8 pt-6 border-t border-border">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3 flex items-center gap-1.5">
        <span className="material-symbols-outlined text-sm">link</span>
        Wiki / bài giảng nhắc tới ({total})
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {data.pages.map((p) => (
          <Link
            key={`page-${p.slug}`}
            href={`/wiki/${p.slug}${linkSuffix}`}
            className="rounded-xl border bg-card p-3 flex items-center gap-3 shadow-sm hover:shadow-md transition-shadow"
          >
            <span className="material-symbols-outlined text-primary">article</span>
            <div className="min-w-0">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Trang wiki
              </div>
              <div className="text-sm font-medium text-foreground truncate">{p.title}</div>
            </div>
          </Link>
        ))}
        {data.lessons.map((l) => (
          <Link
            key={`lesson-${l.id}`}
            href={`/chess/lessons/${l.id}`}
            className="rounded-xl border bg-card p-3 flex items-center gap-3 shadow-sm hover:shadow-md transition-shadow"
          >
            <span className="material-symbols-outlined text-primary">menu_book</span>
            <div className="min-w-0">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Bài giảng
              </div>
              <div className="text-sm font-medium text-foreground truncate">{l.title}</div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
