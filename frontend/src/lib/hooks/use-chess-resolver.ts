"use client";

import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";

export type ChessLinkType = "game" | "position" | "puzzle" | "study";

export type ChessLinkMeta = {
  token: string;
  exists: boolean;
  type?: ChessLinkType;
  id?: string;
  slug?: string | null;
  title?: string;
  subtitle?: string | null;
  route?: string;
  fen?: string;
  eval_cp?: number | null;
  side_to_move?: string;
  result?: string | null;
};

export type ChessResolverState = {
  byToken: Record<string, ChessLinkMeta>;
  loading: boolean;
};

const EMPTY: ChessResolverState = { byToken: {}, loading: false };

/**
 * Batch-resolve `[[game:…]]` / `![[position:…]]` wikilink tokens found in wiki
 * content to chip/embed metadata. Mirrors useImageResolver: one POST per unique
 * set of tokens, re-runs when the set changes.
 */
export function useChessResolver(tokens: string[]): ChessResolverState {
  const [state, setState] = useState<ChessResolverState>(EMPTY);
  const reqId = useRef(0);

  // Stable key for dependency comparison (sorted, deduped).
  const key = Array.from(new Set(tokens)).sort().join(",");

  useEffect(() => {
    if (!key) {
      setState(EMPTY);
      return;
    }
    const myReq = ++reqId.current;
    setState((s) => ({ ...s, loading: true }));

    api<{ items: ChessLinkMeta[] }>("/api/chess/resolve-links", {
      method: "POST",
      body: { tokens: key.split(",") },
    })
      .then((res) => {
        if (myReq !== reqId.current) return;
        const byToken: Record<string, ChessLinkMeta> = {};
        for (const it of res.items || []) byToken[it.token] = it;
        setState({ byToken, loading: false });
      })
      .catch(() => {
        if (myReq !== reqId.current) return;
        setState({ byToken: {}, loading: false });
      });
  }, [key]);

  return state;
}

export const CHESS_LINK_LABEL: Record<ChessLinkType, string> = {
  game: "Ván cờ",
  position: "Thế cờ",
  puzzle: "Bài tập",
  study: "Bộ học liệu",
};

export const CHESS_LINK_ICON: Record<ChessLinkType, string> = {
  game: "chess",
  position: "grid_on",
  puzzle: "extension",
  study: "library_books",
};
