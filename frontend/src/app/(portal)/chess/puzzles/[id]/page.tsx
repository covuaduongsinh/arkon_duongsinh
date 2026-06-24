"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { PageHeader } from "@/components/shared/page-header";
import { ChessBoard } from "@/components/chess/ChessBoard";
import { ChessBacklinks } from "@/components/chess/ChessBacklinks";
import { WikilinkTokens } from "@/components/chess/WikilinkTokens";
import type { ChessPuzzle } from "@/types/chess";

export default function ChessPuzzleDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [puzzle, setPuzzle] = useState<ChessPuzzle | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  const fetchPuzzle = useCallback(async () => {
    if (!id) return;
    try {
      setPuzzle(await api<ChessPuzzle>(`/api/chess/puzzles/${id}`));
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) setNotFound(true);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchPuzzle();
  }, [fetchPuzzle]);

  if (loading) return <p className="text-sm text-muted-foreground">Đang tải…</p>;
  if (notFound || !puzzle)
    return (
      <>
        <PageHeader title="Không tìm thấy bài tập" />
        <Link href="/chess/puzzles" className="text-sm text-primary hover:underline">
          ← Danh sách bài tập
        </Link>
      </>
    );

  return (
    <>
      <PageHeader
        title={puzzle.title || "Bài tập"}
        description={puzzle.description ?? undefined}
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,420px)_1fr]">
        <div>
          <ChessBoard
            fen={puzzle.fen}
            orientation={puzzle.side_to_move === "b" ? "black" : "white"}
            className="max-w-[400px]"
          />
          <p className="mt-2 text-xs text-muted-foreground">
            {puzzle.side_to_move === "b" ? "Đen" : "Trắng"} đi
            {puzzle.rating != null ? ` · Độ khó ${puzzle.rating}` : ""}
          </p>
          <Link
            href="/chess/puzzles"
            className="mt-3 inline-block text-sm text-primary hover:underline"
          >
            Luyện tập →
          </Link>
        </div>

        <div className="space-y-4">
          {puzzle.themes?.length ? (
            <div className="flex flex-wrap gap-1.5">
              {puzzle.themes.map((th) => (
                <span key={th} className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                  {th}
                </span>
              ))}
            </div>
          ) : null}
          {puzzle.slug ? <WikilinkTokens ns="puzzle" slug={puzzle.slug} /> : null}
        </div>
      </div>

      <ChessBacklinks type="puzzle" id={puzzle.id} />

      <Link href="/chess/puzzles" className="mt-8 inline-block text-sm text-muted-foreground hover:text-foreground">
        ← Danh sách bài tập
      </Link>
    </>
  );
}
