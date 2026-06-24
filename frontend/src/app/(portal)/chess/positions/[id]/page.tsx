"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { PageHeader } from "@/components/shared/page-header";
import { ChessBoard } from "@/components/chess/ChessBoard";
import { ChessBacklinks } from "@/components/chess/ChessBacklinks";
import { WikilinkTokens } from "@/components/chess/WikilinkTokens";
import type { ChessPosition } from "@/types/chess";

export default function ChessPositionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [pos, setPos] = useState<ChessPosition | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  const fetchPos = useCallback(async () => {
    if (!id) return;
    try {
      setPos(await api<ChessPosition>(`/api/chess/positions/${id}`));
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) setNotFound(true);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchPos();
  }, [fetchPos]);

  if (loading) return <p className="text-sm text-muted-foreground">Đang tải…</p>;
  if (notFound || !pos)
    return (
      <>
        <PageHeader title="Không tìm thấy thế cờ" />
        <Link href="/chess/positions" className="text-sm text-primary hover:underline">
          ← Danh sách thế cờ
        </Link>
      </>
    );

  return (
    <>
      <PageHeader title={pos.label || "Thế cờ"} description={pos.description ?? undefined} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,420px)_1fr]">
        <div>
          <ChessBoard fen={pos.fen} className="max-w-[400px]" />
          {pos.eval_cp != null && (
            <p className="mt-2 text-xs text-muted-foreground">
              Eval: {(pos.eval_cp / 100).toFixed(2)} (depth {pos.eval_depth ?? "?"})
            </p>
          )}
          <div className="mt-3 flex flex-wrap gap-3 text-sm">
            <Link
              href={`/chess/analysis?fen=${encodeURIComponent(pos.fen)}`}
              className="text-primary hover:underline"
            >
              Phân tích →
            </Link>
          </div>
        </div>

        <div className="space-y-4">
          {pos.themes?.length ? (
            <div className="flex flex-wrap gap-1.5">
              {pos.themes.map((th) => (
                <span key={th} className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                  {th}
                </span>
              ))}
            </div>
          ) : null}
          <p className="font-mono text-xs text-muted-foreground break-all">{pos.fen}</p>
          {pos.slug ? <WikilinkTokens ns="position" slug={pos.slug} /> : null}
        </div>
      </div>

      <ChessBacklinks type="position" id={pos.id} />

      <Link href="/chess/positions" className="mt-8 inline-block text-sm text-muted-foreground hover:text-foreground">
        ← Danh sách thế cờ
      </Link>
    </>
  );
}
