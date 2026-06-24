"use client";

import React from "react";

import type { ChessLinkType } from "@/lib/hooks/use-chess-resolver";

/**
 * Shows the copy-ready wikilink tokens for a chess entity so coaches can paste
 * them into a wiki page or lesson: `[[ns:slug]]` (link) and `![[ns:slug]]`
 * (embed the board / viewer inline).
 */
export function WikilinkTokens({ ns, slug }: { ns: ChessLinkType; slug: string }) {
  return (
    <div className="rounded-lg border border-border bg-muted/30 p-3">
      <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Chèn vào wiki / bài giảng
      </div>
      <TokenRow label="Liên kết" value={`[[${ns}:${slug}]]`} />
      <TokenRow label="Nhúng" value={`![[${ns}:${slug}]]`} />
    </div>
  );
}

function TokenRow({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = React.useState(false);
  return (
    <div className="flex items-center gap-2 py-0.5">
      <span className="w-20 shrink-0 text-[11px] text-muted-foreground">{label}</span>
      <code className="flex-1 truncate rounded bg-background px-1.5 py-0.5 font-mono text-xs">{value}</code>
      <button
        type="button"
        onClick={() => {
          navigator.clipboard.writeText(value);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}
        className="shrink-0 text-muted-foreground hover:text-foreground"
        title="Sao chép"
      >
        <span className="material-symbols-outlined" style={{ fontSize: 15 }}>
          {copied ? "check" : "content_copy"}
        </span>
      </button>
    </div>
  );
}
