"use client";

import Link from "next/link";
import { Chess } from "chess.js";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { t } from "@/lib/i18n";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/shared/empty-state";
import { ChessBoard } from "@/components/chess/ChessBoard";
import type { ChessPosition, Paginated } from "@/types/chess";

const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

export default function ChessPositionsPage() {
  const { hasPermission } = useAuth();
  const canCreate = hasPermission("chess:create:own_dept") || hasPermission("chess:create:all");

  const [positions, setPositions] = useState<ChessPosition[]>([]);
  const [loading, setLoading] = useState(true);
  const [fen, setFen] = useState("");
  const [label, setLabel] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Local validity preview using chess.js.
  const fenValid = (() => {
    if (!fen.trim()) return null;
    try {
      new Chess(fen.trim());
      return true;
    } catch {
      return false;
    }
  })();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api<Paginated<ChessPosition>>("/api/chess/positions");
      setPositions(data.items);
    } catch {
      setPositions([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function save() {
    setError(null);
    try {
      await api("/api/chess/positions", {
        method: "POST",
        body: { fen: fen.trim(), label: label || null, scope_type: "global" },
      });
      setFen("");
      setLabel("");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to save position");
    }
  }

  return (
    <>
      <PageHeader title={t("Positions")} description={t("Save and revisit FEN positions.")} />

      {canCreate && (
        <div className="space-y-2 rounded-lg border border-black/10 bg-card p-4">
          <div className="flex flex-wrap items-end gap-2">
            <div className="min-w-[280px] flex-1">
              <label className="mb-1 block text-sm font-medium">FEN</label>
              <Input value={fen} onChange={(e) => setFen(e.target.value)} placeholder={START_FEN} className="font-mono text-xs" />
            </div>
            <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Label (optional)" className="min-w-[180px]" />
            <Button onClick={save} disabled={!fen.trim() || fenValid === false}>Save</Button>
          </div>
          {fen.trim() && (
            <p className={`text-xs ${fenValid ? "text-green-700" : "text-destructive"}`}>
              {fenValid ? "Valid FEN" : "Invalid FEN"}
            </p>
          )}
          {fen.trim() && fenValid && (
            <div className="pt-2">
              <ChessBoard fen={fen.trim()} className="max-w-[320px]" />
            </div>
          )}
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : positions.length === 0 ? (
        <EmptyState icon="grid_on" title="No saved positions" description="Save a FEN above to revisit it later." />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {positions.map((p) => (
            <div key={p.id} className="rounded-lg border border-black/10 bg-card p-3">
              <ChessBoard fen={p.fen} className="max-w-[260px]" />
              <div className="mt-2 flex items-center justify-between gap-2">
                <Link href={`/chess/positions/${p.id}`} className="truncate text-sm font-medium hover:text-primary hover:underline">
                  {p.label || "Untitled"}
                </Link>
                <Link href={`/chess/analysis?fen=${encodeURIComponent(p.fen)}`} className="shrink-0 text-xs text-primary hover:underline">
                  Analyze →
                </Link>
              </div>
              {p.eval_cp != null && (
                <p className="mt-1 text-xs text-muted-foreground">Eval: {(p.eval_cp / 100).toFixed(2)} (depth {p.eval_depth ?? "?"})</p>
              )}
            </div>
          ))}
        </div>
      )}

      <Link href="/chess" className="text-sm text-muted-foreground hover:text-foreground">← Back to Chess</Link>
    </>
  );
}
