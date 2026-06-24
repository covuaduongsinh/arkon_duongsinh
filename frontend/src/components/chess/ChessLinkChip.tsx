"use client";

import React from "react";
import Link from "next/link";
import { createPortal } from "react-dom";

import { ChessBoard } from "@/components/chess/ChessBoard";
import {
  CHESS_LINK_ICON,
  CHESS_LINK_LABEL,
  type ChessLinkMeta,
  type ChessLinkType,
} from "@/lib/hooks/use-chess-resolver";

/**
 * Inline chip rendered for a `[[game:…]]` / `[[position:…]]` wikilink. Shows a
 * type icon + title, links to the entity's page, and (for positions/puzzles)
 * reveals a mini board preview on hover via a body-level portal — so the board's
 * <div> never nests inside the surrounding <p>.
 */
export function ChessLinkChip({
  meta,
  token,
  fallback,
  loading,
  linkSuffix = "",
}: {
  meta?: ChessLinkMeta;
  token: string;
  fallback?: React.ReactNode;
  loading?: boolean;
  linkSuffix?: string;
}) {
  const [coords, setCoords] = React.useState<{ top: number; left: number } | null>(null);
  const ref = React.useRef<HTMLSpanElement>(null);

  const ns = (token.split(":")[0] || "game") as ChessLinkType;
  const icon = CHESS_LINK_ICON[ns] ?? "chess";
  const exists = !!meta?.exists;
  const label = exists ? meta!.title : fallback ?? token;
  const previewFen =
    exists && (meta!.type === "position" || meta!.type === "puzzle") ? meta!.fen : undefined;

  const onEnter = () => {
    const el = ref.current;
    if (el) {
      const r = el.getBoundingClientRect();
      setCoords({ top: r.bottom + 6, left: r.left });
    }
  };
  const onLeave = () => setCoords(null);

  const chipClass = exists
    ? "text-primary border-primary/30 bg-primary/5 hover:bg-primary/10"
    : "text-muted-foreground border-border bg-muted/40";

  const body = (
    <span
      ref={ref}
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
      className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-px text-[0.85em] align-baseline transition-colors ${chipClass}`}
      title={!exists ? (loading ? "Đang tải…" : "Không tìm thấy nội dung cờ") : undefined}
    >
      <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
        {icon}
      </span>
      <span className="truncate max-w-[18rem]">{label}</span>
    </span>
  );

  const card =
    coords && exists && typeof window !== "undefined"
      ? createPortal(
          <div
            style={{ position: "fixed", top: coords.top, left: coords.left, zIndex: 120 }}
            className="rounded-lg border border-border bg-popover text-popover-foreground shadow-lg p-2 w-[220px] pointer-events-none"
          >
            {previewFen ? <ChessBoard fen={previewFen} className="w-full" /> : null}
            <div className="mt-1.5 text-xs font-medium truncate">{meta!.title}</div>
            {meta!.subtitle ? (
              <div className="text-[11px] text-muted-foreground truncate">{meta!.subtitle}</div>
            ) : null}
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground mt-0.5">
              {CHESS_LINK_LABEL[meta!.type as ChessLinkType] ?? "Cờ vua"}
            </div>
          </div>,
          document.body,
        )
      : null;

  if (!exists || !meta?.route) {
    return <>{body}</>;
  }
  return (
    <>
      <Link href={`${meta.route}${linkSuffix}`} className="no-underline">
        {body}
      </Link>
      {card}
    </>
  );
}
