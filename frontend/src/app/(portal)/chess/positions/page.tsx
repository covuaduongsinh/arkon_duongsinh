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
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { EmptyState } from "@/components/shared/empty-state";
import { ChessBoard } from "@/components/chess/ChessBoard";
import type { ChessPosition, PositionFacets, Paginated } from "@/types/chess";

const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

// Difficulty bands → (min, max) sent to the API.
const DIFFICULTY_BANDS: Record<string, { min?: number; max?: number; label: string }> = {
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
  { value: "difficulty_asc", label: "Độ khó tăng dần" },
  { value: "difficulty_desc", label: "Độ khó giảm dần" },
  { value: "pieces_asc", label: "Ít quân trước" },
  { value: "eval", label: "Lợi thế Trắng" },
  { value: "label", label: "Theo tên (A–Z)" },
];

const PAGE_SIZE = 24;

export default function ChessPositionsPage() {
  const { hasPermission } = useAuth();
  const canCreate = hasPermission("chess:create:own_dept") || hasPermission("chess:create:all");

  const [positions, setPositions] = useState<ChessPosition[]>([]);
  const [facets, setFacets] = useState<PositionFacets | null>(null);
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
  const [diffBand, setDiffBand] = useState("");
  const [pieceBand, setPieceBand] = useState("");
  const [sort, setSort] = useState("recent");

  const load = useCallback(
    async (p: number, opts: {
      search: string; themes: string[]; side: string; source: string;
      opening: string; diffBand: string; pieceBand: string; sort: string;
    }) => {
      setLoading(true);
      try {
        const params = new URLSearchParams({
          page: String(p), page_size: String(PAGE_SIZE), sort: opts.sort,
        });
        if (opts.search) params.set("search", opts.search);
        opts.themes.forEach((th) => params.append("themes", th));
        if (opts.side) params.set("side", opts.side);
        if (opts.source) params.set("source", opts.source);
        if (opts.opening) params.set("opening", opts.opening);
        const band = DIFFICULTY_BANDS[opts.diffBand];
        if (band?.min != null) params.set("min_difficulty", String(band.min));
        if (band?.max != null) params.set("max_difficulty", String(band.max));
        const pband = PIECE_BANDS[opts.pieceBand];
        if (pband?.max != null) params.set("max_pieces", String(pband.max));
        const data = await api<Paginated<ChessPosition>>(`/api/chess/positions?${params}`);
        setPositions(data.items);
        setTotal(data.total);
        setTotalPages(data.total_pages);
        setPage(data.page);
      } catch {
        setPositions([]);
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  const opts = { search, themes: activeThemes, side, source, opening, diffBand, pieceBand, sort };

  // Re-fetch whenever a non-text filter changes; search submits via the form.
  useEffect(() => {
    load(1, { search, themes: activeThemes, side, source, opening, diffBand, pieceBand, sort });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeThemes, side, source, opening, diffBand, pieceBand, sort]);

  useEffect(() => {
    api<PositionFacets>("/api/chess/positions/facets").then(setFacets).catch(() => setFacets(null));
  }, []);

  function toggleTheme(th: string) {
    setActiveThemes((prev) => (prev.includes(th) ? prev.filter((x) => x !== th) : [...prev, th]));
  }

  return (
    <>
      <PageHeader
        title={t("Positions")}
        description={`Thư viện thế cờ — ${total} thế cờ`}
        action={canCreate ? <AddButton onCreated={() => load(1, opts)} /> : undefined}
      />

      {/* Search */}
      <form
        className="flex gap-2"
        onSubmit={(e) => { e.preventDefault(); load(1, opts); }}
      >
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
        <FilterSelect value={diffBand} onChange={setDiffBand} placeholder="Độ khó"
          options={Object.entries(DIFFICULTY_BANDS).map(([value, b]) => ({ value, label: b.label }))} />
        <FilterSelect value={pieceBand} onChange={setPieceBand} placeholder="Số quân"
          options={Object.entries(PIECE_BANDS).map(([value, b]) => ({ value, label: b.label }))} />
        <FilterSelect value={source} onChange={setSource} placeholder="Nguồn"
          options={[{ value: "", label: "Mọi nguồn" }, { value: "manual", label: "Thủ công" }, { value: "puzzle", label: "Puzzle · Lichess" }, { value: "game", label: "Từ ván cờ" }]} />
        {facets && facets.openings.length > 0 && (
          <FilterSelect value={opening} onChange={setOpening} placeholder="Khai cuộc"
            options={[{ value: "", label: "Mọi khai cuộc" }, ...facets.openings.map((o) => ({ value: o.value, label: `${o.value} (${o.count})` }))]} />
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
      ) : positions.length === 0 ? (
        <EmptyState icon="grid_on" title="Không có thế cờ phù hợp" description="Đổi bộ lọc, hoặc lưu/nhập thế cờ để bắt đầu." />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {positions.map((p) => (
            <div key={p.id} className="rounded-lg border border-black/10 bg-card p-3">
              <ChessBoard fen={p.fen} className="max-w-full" />
              <div className="mt-2 flex items-center justify-between gap-2">
                <Link href={`/chess/positions/${p.id}`} className="truncate text-sm font-medium hover:text-primary hover:underline">
                  {p.label || "Chưa đặt tên"}
                </Link>
                <Link href={`/chess/analysis?fen=${encodeURIComponent(p.fen)}`} className="shrink-0 text-xs text-primary hover:underline">
                  Phân tích →
                </Link>
              </div>
              <div className="mt-1.5 flex flex-wrap items-center gap-1">
                {p.difficulty != null && (
                  <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[11px] text-amber-800">★ {p.difficulty}</span>
                )}
                {p.piece_count != null && (
                  <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">{p.piece_count} quân</span>
                )}
                {p.side_to_move && (
                  <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">{p.side_to_move === "w" ? "Trắng đi" : "Đen đi"}</span>
                )}
                {p.themes?.slice(0, 2).map((th) => (
                  <button key={th} onClick={() => toggleTheme(th)} className="rounded-full bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground hover:bg-muted/70">
                    {th}
                  </button>
                ))}
              </div>
              <div className="mt-1 flex items-center justify-between text-[11px] text-muted-foreground">
                <span>{p.opening_name || (p.source === "puzzle" ? "Lichess" : "")}</span>
                {p.source_puzzle_id && (
                  <Link href={`/chess/puzzles/${p.source_puzzle_id}`} className="text-primary hover:underline">Giải puzzle →</Link>
                )}
              </div>
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

function AddButton({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [fen, setFen] = useState("");
  const [label, setLabel] = useState("");
  const [themes, setThemes] = useState("");
  const [description, setDescription] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [opening, setOpening] = useState("");
  const [error, setError] = useState<string | null>(null);

  const fenValid = (() => {
    if (!fen.trim()) return null;
    try { new Chess(fen.trim()); return true; } catch { return false; }
  })();

  async function save() {
    setError(null);
    try {
      await api("/api/chess/positions", {
        method: "POST",
        body: {
          fen: fen.trim(),
          label: label || null,
          description: description || null,
          themes: themes.split(",").map((s) => s.trim()).filter(Boolean),
          difficulty: difficulty ? Number(difficulty) : null,
          opening_name: opening || null,
          scope_type: "global",
        },
      });
      setOpen(false);
      setFen(""); setLabel(""); setThemes(""); setDescription(""); setDifficulty(""); setOpening("");
      onCreated();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không lưu được thế cờ");
    }
  }

  return (
    <div className="relative">
      <Button onClick={() => setOpen((o) => !o)}>
        <span className="material-symbols-outlined text-[18px]">add</span> Thêm thế cờ
      </Button>
      {open && (
    <div className="absolute right-0 z-20 mt-2 w-[340px] space-y-2 rounded-lg border border-black/10 bg-card p-4 text-left shadow-lg">
      <div>
        <label className="mb-1 block text-sm font-medium">FEN</label>
        <Input value={fen} onChange={(e) => setFen(e.target.value)} placeholder={START_FEN} className="font-mono text-xs" />
        {fen.trim() && (
          <p className={`mt-1 text-xs ${fenValid ? "text-green-700" : "text-destructive"}`}>{fenValid ? "FEN hợp lệ" : "FEN không hợp lệ"}</p>
        )}
      </div>
      {fen.trim() && fenValid && <ChessBoard fen={fen.trim()} className="max-w-[260px]" />}
      <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Tên (tuỳ chọn)" />
      <Input value={themes} onChange={(e) => setThemes(e.target.value)} placeholder="Tag, cách nhau bằng dấu phẩy" />
      <div className="flex gap-2">
        <Input value={difficulty} onChange={(e) => setDifficulty(e.target.value)} placeholder="Độ khó" type="number" className="w-28" />
        <Input value={opening} onChange={(e) => setOpening(e.target.value)} placeholder="Khai cuộc" />
      </div>
      <Textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Mô tả (tuỳ chọn)" rows={2} />
      {error && <p className="text-sm text-destructive">{error}</p>}
      <div className="flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={() => setOpen(false)}>Huỷ</Button>
        <Button size="sm" onClick={save} disabled={!fen.trim() || fenValid === false}>Lưu</Button>
      </div>
    </div>
      )}
    </div>
  );
}
