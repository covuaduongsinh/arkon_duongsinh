"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { t } from "@/lib/i18n";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { EmptyState } from "@/components/shared/empty-state";
import { ChessBoard } from "@/components/chess/ChessBoard";
import type { ChessPuzzle, PuzzleFacets, Paginated } from "@/types/chess";

// Rating bands → (min, max) sent to the API.
const RATING_BANDS: Record<string, { min?: number; max?: number; label: string }> = {
  "": { label: "Mọi độ khó" },
  easy: { max: 1200, label: "Dễ (≤1200)" },
  mid: { min: 1200, max: 1800, label: "Trung bình (1200–1800)" },
  hard: { min: 1800, max: 2200, label: "Khó (1800–2200)" },
  expert: { min: 2200, label: "Rất khó (≥2200)" },
};

const PIECE_BANDS: Record<string, { max?: number; label: string }> = {
  "": { label: "Mọi số quân" },
  endgame: { max: 7, label: "Tàn cuộc (≤7 quân)" },
  few: { max: 12, label: "Ít quân (≤12)" },
};

const SORTS: { value: string; label: string }[] = [
  { value: "recent", label: "Mới nhất" },
  { value: "popularity", label: "Phổ biến" },
  { value: "plays", label: "Nhiều lượt giải" },
  { value: "rating_asc", label: "Độ khó tăng dần" },
  { value: "rating_desc", label: "Độ khó giảm dần" },
  { value: "pieces_asc", label: "Ít quân trước" },
];

const PAGE_SIZE = 24;

export default function ChessPuzzlesPage() {
  const { hasPermission } = useAuth();
  const canCoach = hasPermission("chess:coach");

  const [puzzles, setPuzzles] = useState<ChessPuzzle[]>([]);
  const [facets, setFacets] = useState<PuzzleFacets | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);

  // Filters
  const [search, setSearch] = useState("");
  const [activeThemes, setActiveThemes] = useState<string[]>([]);
  const [side, setSide] = useState("");
  const [source, setSource] = useState("");
  const [opening, setOpening] = useState("");
  const [ratingBand, setRatingBand] = useState("");
  const [pieceBand, setPieceBand] = useState("");
  const [sort, setSort] = useState("recent");
  const [includeDrafts, setIncludeDrafts] = useState(false);

  const opts = { search, themes: activeThemes, side, source, opening, ratingBand, pieceBand, sort, includeDrafts };

  const load = useCallback(
    async (p: number, o: typeof opts) => {
      setLoading(true);
      try {
        const params = new URLSearchParams({
          page: String(p), page_size: String(PAGE_SIZE), sort: o.sort,
        });
        if (o.search) params.set("search", o.search);
        o.themes.forEach((th) => params.append("themes", th));
        if (o.side) params.set("side", o.side);
        if (o.source) params.set("source", o.source);
        if (o.opening) params.set("opening", o.opening);
        if (o.includeDrafts) params.set("include_drafts", "true");
        const band = RATING_BANDS[o.ratingBand];
        if (band?.min != null) params.set("min_rating", String(band.min));
        if (band?.max != null) params.set("max_rating", String(band.max));
        const pband = PIECE_BANDS[o.pieceBand];
        if (pband?.max != null) params.set("max_pieces", String(pband.max));
        const data = await api<Paginated<ChessPuzzle>>(`/api/chess/puzzles?${params}`);
        setPuzzles(data.items);
        setTotal(data.total);
        setTotalPages(data.total_pages);
        setPage(data.page);
      } catch {
        setPuzzles([]);
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  // Re-fetch whenever a non-text filter changes; search submits via the form.
  useEffect(() => {
    load(1, { search, themes: activeThemes, side, source, opening, ratingBand, pieceBand, sort, includeDrafts });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeThemes, side, source, opening, ratingBand, pieceBand, sort, includeDrafts]);

  useEffect(() => {
    const q = includeDrafts ? "?include_drafts=true" : "";
    api<PuzzleFacets>(`/api/chess/puzzles/facets${q}`).then(setFacets).catch(() => setFacets(null));
  }, [includeDrafts]);

  function toggleTheme(th: string) {
    setActiveThemes((prev) => (prev.includes(th) ? prev.filter((x) => x !== th) : [...prev, th]));
  }

  return (
    <>
      <PageHeader
        title="Thư viện bài tập"
        description={`${total} bài tập`}
        action={
          <div className="flex gap-2">
            <Link href="/chess/puzzles/train">
              <Button variant="outline">
                <span className="material-symbols-outlined text-[18px]">extension</span>
                Luyện tập ngẫu nhiên
              </Button>
            </Link>
            {canCoach && (
              <Link href="/chess/puzzles/new">
                <Button>
                  <span className="material-symbols-outlined text-[18px]">add</span>
                  Tạo bài tập
                </Button>
              </Link>
            )}
          </div>
        }
      />

      {/* Search */}
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); load(1, opts); }}>
        <Input
          placeholder="Tìm theo tên, mô tả, khai cuộc…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-sm"
        />
        <Button type="submit" variant="outline">{t("Search")}</Button>
      </form>

      {/* Filter row */}
      <div className="flex flex-wrap items-center gap-2">
        <FilterSelect value={side} onChange={setSide} placeholder="Lượt đi"
          options={[{ value: "", label: "Cả hai lượt" }, { value: "w", label: "Trắng đi" }, { value: "b", label: "Đen đi" }]} />
        <FilterSelect value={ratingBand} onChange={setRatingBand} placeholder="Độ khó"
          options={Object.entries(RATING_BANDS).map(([value, b]) => ({ value, label: b.label }))} />
        <FilterSelect value={pieceBand} onChange={setPieceBand} placeholder="Số quân"
          options={Object.entries(PIECE_BANDS).map(([value, b]) => ({ value, label: b.label }))} />
        <FilterSelect value={source} onChange={setSource} placeholder="Nguồn"
          options={[{ value: "", label: "Mọi nguồn" }, { value: "manual", label: "Thủ công" }, { value: "lichess", label: "Lichess" }]} />
        {facets && facets.openings.length > 0 && (
          <FilterSelect value={opening} onChange={setOpening} placeholder="Khai cuộc"
            options={[{ value: "", label: "Mọi khai cuộc" }, ...facets.openings.map((o) => ({ value: o.value, label: `${o.value} (${o.count})` }))]} />
        )}
        {canCoach && (
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <input type="checkbox" checked={includeDrafts} onChange={(e) => setIncludeDrafts(e.target.checked)} />
            Hiện bản nháp
          </label>
        )}
        <div className="ml-auto">
          <FilterSelect value={sort} onChange={setSort} placeholder="Sắp xếp" options={SORTS} />
        </div>
      </div>

      {/* Theme facet chips */}
      {facets && facets.themes.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {facets.themes.slice(0, 28).map((th) => {
            const on = activeThemes.includes(th.value);
            return (
              <button
                key={th.value}
                onClick={() => toggleTheme(th.value)}
                className={`rounded-full px-2.5 py-0.5 text-xs transition-colors ${
                  on ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-muted/70"
                }`}
              >
                {th.value} <span className="opacity-60">{th.count}</span>
              </button>
            );
          })}
          {activeThemes.length > 0 && (
            <button onClick={() => setActiveThemes([])} className="text-xs text-primary hover:underline">
              Xoá lọc tag
            </button>
          )}
        </div>
      )}

      {/* Results */}
      {loading ? (
        <p className="text-sm text-muted-foreground">Đang tải…</p>
      ) : puzzles.length === 0 ? (
        <EmptyState icon="extension" title="Không có bài tập phù hợp" description="Đổi bộ lọc, tạo bài, hoặc nhập từ Lichess để bắt đầu." />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {puzzles.map((p) => (
            <div key={p.id} className="rounded-lg border border-black/10 bg-card p-3">
              <ChessBoard fen={p.fen} orientation={p.side_to_move === "b" ? "black" : "white"} interactive={false} className="max-w-full" />
              <div className="mt-2 flex items-center justify-between gap-2">
                <Link href={`/chess/puzzles/${p.id}`} className="truncate text-sm font-medium hover:text-primary hover:underline">
                  {p.title || "Bài tập"}
                </Link>
                <Link href={`/chess/puzzles/${p.id}`} className="shrink-0 text-xs text-primary hover:underline">
                  Giải →
                </Link>
              </div>
              <div className="mt-1.5 flex flex-wrap items-center gap-1">
                {p.rating != null && (
                  <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[11px] text-amber-800">★ {p.rating}</span>
                )}
                <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">{p.side_to_move === "w" ? "Trắng đi" : "Đen đi"}</span>
                {!p.is_published && (
                  <span className="rounded bg-orange-100 px-1.5 py-0.5 text-[11px] text-orange-800">Nháp</span>
                )}
                {p.themes?.slice(0, 2).map((th) => (
                  <button key={th} onClick={() => toggleTheme(th)} className="rounded-full bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground hover:bg-muted/70">
                    {th}
                  </button>
                ))}
              </div>
              {p.opening_name && (
                <p className="mt-1 truncate text-[11px] text-muted-foreground">{p.opening_name}</p>
              )}
            </div>
          ))}
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => load(page - 1, opts)}>{t("Previous")}</Button>
          <span className="text-sm text-muted-foreground">Trang {page} / {totalPages}</span>
          <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => load(page + 1, opts)}>{t("Next")}</Button>
        </div>
      )}

      <Link href="/chess" className="text-sm text-muted-foreground hover:text-foreground">← {t("Back to Chess")}</Link>
    </>
  );
}

function FilterSelect({
  value, onChange, placeholder, options,
}: {
  value: string; onChange: (v: string) => void; placeholder: string;
  options: { value: string; label: string }[];
}) {
  return (
    <Select value={value} onValueChange={(v) => onChange(v ?? "")}>
      <SelectTrigger className="h-8 bg-background"><SelectValue placeholder={placeholder} /></SelectTrigger>
      <SelectContent>
        {options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
      </SelectContent>
    </Select>
  );
}
