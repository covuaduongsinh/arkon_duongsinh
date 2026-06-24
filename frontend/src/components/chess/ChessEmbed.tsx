"use client";

import React from "react";
import Link from "next/link";

import { ChessBoard } from "@/components/chess/ChessBoard";
import { PgnViewer } from "@/components/chess/PgnViewer";
import { api } from "@/lib/api";
import { CHESS_LINK_LABEL, type ChessLinkMeta, type ChessLinkType } from "@/lib/hooks/use-chess-resolver";

function Shell({ children, dashed }: { children: React.ReactNode; dashed?: boolean }) {
  return (
    <div
      className={`my-5 rounded-xl border ${dashed ? "border-dashed" : "border-border"} bg-card/40 p-3 text-sm text-muted-foreground`}
    >
      {children}
    </div>
  );
}

/**
 * Inline embed for `![[game:…]]` / `![[position:…]]`. Positions & puzzles render
 * the board directly from resolved metadata; games fetch their full PGN and use
 * the interactive PgnViewer; study sets render a compact link card. The wiki
 * `p` renderer unwraps these so the block markup doesn't nest inside a <p>.
 */
export function ChessEmbed({
  meta,
  token,
  loading,
  linkSuffix = "",
}: {
  meta?: ChessLinkMeta;
  token: string;
  loading?: boolean;
  linkSuffix?: string;
}) {
  const [pgn, setPgn] = React.useState<string | null>(null);
  const [err, setErr] = React.useState(false);

  const isGame = meta?.exists && meta.type === "game" && meta.id;
  React.useEffect(() => {
    if (!isGame) return;
    let cancelled = false;
    api<{ pgn: string }>(`/api/chess/games/${meta!.id}`)
      .then((g) => {
        if (!cancelled) setPgn(g.pgn);
      })
      .catch(() => {
        if (!cancelled) setErr(true);
      });
    return () => {
      cancelled = true;
    };
  }, [isGame, meta]);

  if (!meta) {
    return <Shell>{loading ? "Đang tải nội dung cờ…" : <code>{token}</code>}</Shell>;
  }
  if (!meta.exists) {
    return (
      <Shell dashed>
        Không tìm thấy nội dung cờ: <code>{token}</code>
      </Shell>
    );
  }

  const header = (
    <div className="flex items-center justify-between mb-2 gap-2">
      <div className="text-sm font-medium text-foreground truncate">{meta.title}</div>
      {meta.route ? (
        <Link
          href={`${meta.route}${linkSuffix}`}
          className="text-xs text-primary hover:underline shrink-0 whitespace-nowrap"
        >
          Mở →
        </Link>
      ) : null}
    </div>
  );

  if (meta.type === "position" || meta.type === "puzzle") {
    return (
      <div className="my-5 rounded-xl border border-border bg-card/40 p-3 max-w-[400px]">
        {header}
        <ChessBoard
          fen={meta.fen!}
          orientation={meta.side_to_move === "b" ? "black" : "white"}
          className="max-w-[360px]"
        />
        {meta.subtitle ? <div className="mt-2 text-xs text-muted-foreground">{meta.subtitle}</div> : null}
      </div>
    );
  }

  if (meta.type === "game") {
    return (
      <div className="my-5 rounded-xl border border-border bg-card/40 p-3">
        {header}
        {err ? (
          <div className="text-sm text-muted-foreground">Không tải được ván cờ.</div>
        ) : pgn ? (
          <PgnViewer pgn={pgn} />
        ) : (
          <div className="text-sm text-muted-foreground">Đang tải ván cờ…</div>
        )}
      </div>
    );
  }

  // study set — compact link card
  return (
    <Link
      href={`${meta.route}${linkSuffix}`}
      className="my-5 block rounded-xl border border-border bg-card p-4 hover:shadow-md transition-shadow no-underline"
    >
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
        {CHESS_LINK_LABEL[meta.type as ChessLinkType] ?? "Bộ học liệu"}
        {meta.subtitle ? ` · ${meta.subtitle}` : ""}
      </div>
      <div className="text-sm font-medium text-foreground">{meta.title}</div>
    </Link>
  );
}
