"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { t } from "@/lib/i18n";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/shared/empty-state";
import type { ChessGameSummary, Paginated } from "@/types/chess";

export default function ChessGamesPage() {
  const router = useRouter();
  const { hasPermission } = useAuth();
  const canImport = hasPermission("chess:create:own_dept") || hasPermission("chess:create:all");

  const [games, setGames] = useState<ChessGameSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (p = 1, s = "") => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(p), page_size: "20" });
      if (s) params.set("search", s);
      const data = await api<Paginated<ChessGameSummary>>(`/api/chess/games?${params}`);
      setGames(data.items);
      setTotal(data.total);
      setTotalPages(data.total_pages);
      setPage(data.page);
    } catch {
      setGames([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(1, "");
  }, [load]);

  return (
    <>
      <PageHeader
        title={t("Games")}
        description={`${total} ván trong kho`}
        action={
          canImport && (
            <Button onClick={() => router.push("/chess/games/import")}>
              <span className="material-symbols-outlined text-[18px]">upload_file</span>
              {t("Import PGN")}
            </Button>
          )
        }
      />

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          load(1, search);
        }}
      >
        <Input
          placeholder={t("Search by player, opening, or event…")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-sm"
        />
        <Button type="submit" variant="outline">{t("Search")}</Button>
      </form>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : games.length === 0 ? (
        <EmptyState
          icon="deployed_code"
          title={t("No games yet")}
          description={t("Import a PGN file to build your game database.")}
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-black/10">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-left text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">{t("White")}</th>
                <th className="px-3 py-2 font-medium">{t("Black")}</th>
                <th className="px-3 py-2 font-medium">{t("Result")}</th>
                <th className="px-3 py-2 font-medium">{t("Opening")}</th>
                <th className="px-3 py-2 font-medium">{t("Date")}</th>
                <th className="px-3 py-2 font-medium">{t("Moves")}</th>
              </tr>
            </thead>
            <tbody>
              {games.map((g) => (
                <tr
                  key={g.id}
                  onClick={() => router.push(`/chess/games/${g.id}`)}
                  className="cursor-pointer border-t border-black/[0.06] hover:bg-muted/30"
                >
                  <td className="px-3 py-2">{g.white || "—"}{g.white_elo ? ` (${g.white_elo})` : ""}</td>
                  <td className="px-3 py-2">{g.black || "—"}{g.black_elo ? ` (${g.black_elo})` : ""}</td>
                  <td className="px-3 py-2 tabular-nums">{g.result || "*"}</td>
                  <td className="px-3 py-2 text-muted-foreground">{g.eco ? `${g.eco} ` : ""}{g.opening_name || ""}</td>
                  <td className="px-3 py-2 text-muted-foreground">{g.played_at || "—"}</td>
                  <td className="px-3 py-2 tabular-nums text-muted-foreground">{Math.ceil(g.ply_count / 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => load(page - 1, search)}>
            {t("Previous")}
          </Button>
          <span className="text-sm text-muted-foreground">Trang {page} / {totalPages}</span>
          <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => load(page + 1, search)}>
            {t("Next")}
          </Button>
        </div>
      )}

      <Link href="/chess" className="text-sm text-muted-foreground hover:text-foreground">
        {t("Back to Chess")}
      </Link>
    </>
  );
}
