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
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { EmptyState } from "@/components/shared/empty-state";
import { ChessBoard } from "@/components/chess/ChessBoard";
import type { ChessGameSummary, GameFacets, Paginated } from "@/types/chess";

const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

const ELO_BANDS: Record<string, { min?: number; max?: number; label: string }> = {
  "": { label: "Mọi ELO" },
  u1600: { max: 1599, label: "Dưới 1600" },
  "1600": { min: 1600, max: 1999, label: "1600–2000" },
  "2000": { min: 2000, max: 2399, label: "2000–2400" },
  "2400": { min: 2400, label: "≥ 2400" },
};

const LENGTH_BANDS: Record<string, { minPly?: number; maxPly?: number; label: string }> = {
  "": { label: "Mọi độ dài" },
  short: { maxPly: 39, label: "Ngắn (<20 nước)" },
  medium: { minPly: 40, maxPly: 80, label: "Trung bình (20–40)" },
  long: { minPly: 81, label: "Dài (>40 nước)" },
};

const RESULTS = [
  { value: "", label: "Mọi kết quả" },
  { value: "1-0", label: "Trắng thắng (1-0)" },
  { value: "0-1", label: "Đen thắng (0-1)" },
  { value: "1/2-1/2", label: "Hòa (½-½)" },
];

const ANALYZED = [
  { value: "", label: "Phân tích?" },
  { value: "done", label: "Đã phân tích" },
  { value: "none", label: "Chưa phân tích" },
];

const SORTS = [
  { value: "recent", label: "Mới nhất" },
  { value: "popularity", label: "Phổ biến (lượt xem)" },
  { value: "elo_desc", label: "ELO cao nhất" },
  { value: "year_desc", label: "Năm mới nhất" },
  { value: "ply_desc", label: "Dài nhất" },
  { value: "brilliants_desc", label: "Nhiều nước hay (!!)" },
  { value: "blunders_desc", label: "Nhiều nước sai (??)" },
  { value: "title", label: "Theo tên" },
];

const PAGE_SIZE = 24;

export default function ChessGamesPage() {
  const router = useRouter();
  const { hasPermission } = useAuth();
  const canImport = hasPermission("chess:create:own_dept") || hasPermission("chess:create:all");
  const canCoach = hasPermission("chess:coach");

  const [games, setGames] = useState<ChessGameSummary[]>([]);
  const [facets, setFacets] = useState<GameFacets | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<"table" | "grid">("table");

  // Filters
  const [search, setSearch] = useState("");
  const [white, setWhite] = useState("");
  const [black, setBlack] = useState("");
  const [result, setResult] = useState("");
  const [opening, setOpening] = useState("");
  const [event, setEvent] = useState("");
  const [site, setSite] = useState("");
  const [source, setSource] = useState("");
  const [eloBand, setEloBand] = useState("");
  const [lengthBand, setLengthBand] = useState("");
  const [analyzed, setAnalyzed] = useState("");
  const [activeThemes, setActiveThemes] = useState<string[]>([]);
  const [named, setNamed] = useState(false);
  const [sort, setSort] = useState("recent");
  const [draftsOnly, setDraftsOnly] = useState(false);

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  const opts = {
    search, white, black, result, opening, event, site, source,
    eloBand, lengthBand, analyzed, themes: activeThemes, named, sort, draftsOnly,
  };

  useEffect(() => {
    const v = localStorage.getItem("chess_games_view");
    if (v === "grid" || v === "table") setView(v);
  }, []);

  function setViewPersist(v: "table" | "grid") {
    setView(v);
    localStorage.setItem("chess_games_view", v);
  }

  const load = useCallback(async (p: number, o: typeof opts) => {
    setLoading(true);
    setSelected(new Set());
    try {
      const params = new URLSearchParams({ page: String(p), page_size: String(PAGE_SIZE), sort: o.sort });
      if (o.search) params.set("search", o.search);
      if (o.white) params.set("white", o.white);
      if (o.black) params.set("black", o.black);
      if (o.result) params.set("result", o.result);
      if (o.opening) params.set("opening", o.opening);
      if (o.event) params.set("event", o.event);
      if (o.site) params.set("site", o.site);
      if (o.source) params.set("source_game", o.source);
      if (o.analyzed) params.set("analysis_status", o.analyzed);
      if (o.named) params.set("named", "true");
      o.themes.forEach((th) => params.append("themes", th));
      const elo = ELO_BANDS[o.eloBand];
      if (elo?.min != null) params.set("min_elo", String(elo.min));
      if (elo?.max != null) params.set("max_elo", String(elo.max));
      const len = LENGTH_BANDS[o.lengthBand];
      if (len?.minPly != null) params.set("min_ply", String(len.minPly));
      if (len?.maxPly != null) params.set("max_ply", String(len.maxPly));
      if (o.draftsOnly) params.set("drafts_only", "true");
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

  // Re-fetch when a non-text filter changes; text inputs submit via the form.
  useEffect(() => {
    load(1, opts);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result, opening, event, site, source, eloBand, lengthBand, analyzed, activeThemes, named, sort, draftsOnly]);

  useEffect(() => {
    const q = draftsOnly ? "?drafts_only=true" : "";
    api<GameFacets>(`/api/chess/games/facets${q}`).then(setFacets).catch(() => setFacets(null));
  }, [draftsOnly]);

  function toggleTheme(th: string) {
    setActiveThemes((prev) => (prev.includes(th) ? prev.filter((x) => x !== th) : [...prev, th]));
  }
  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  async function togglePublishOne(g: ChessGameSummary) {
    try {
      await api(`/api/chess/games/${g.id}`, { method: "PATCH", body: { is_published: !g.is_published } });
      // Current views are publish-filtered → the game no longer matches; drop it.
      setGames((prev) => prev.filter((x) => x.id !== g.id));
      setTotal((n) => Math.max(0, n - 1));
      setSelected((prev) => {
        if (!prev.has(g.id)) return prev;
        const n = new Set(prev); n.delete(g.id); return n;
      });
    } catch {
      /* ignore */
    }
  }

  async function bulkPublish(publish: boolean) {
    const ids = [...selected];
    if (ids.length === 0) return;
    setBulkBusy(true);
    try {
      await api("/api/chess/games/bulk-publish", { method: "POST", body: { ids, publish } });
      await load(page, opts);
    } catch {
      /* ignore */
    } finally {
      setBulkBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title={t("Games")}
        description={`${total} ván trong thư viện`}
        action={
          <div className="flex gap-2">
            <div className="inline-flex rounded-md border border-black/10 p-0.5">
              <button
                onClick={() => setViewPersist("table")}
                className={`rounded px-2 py-1 text-sm ${view === "table" ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}
                title="Bảng"
              >
                <span className="material-symbols-outlined text-[18px]">table_rows</span>
              </button>
              <button
                onClick={() => setViewPersist("grid")}
                className={`rounded px-2 py-1 text-sm ${view === "grid" ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}
                title="Lưới thẻ"
              >
                <span className="material-symbols-outlined text-[18px]">grid_view</span>
              </button>
            </div>
            {canImport && (
              <Button onClick={() => router.push("/chess/games/import")}>
                <span className="material-symbols-outlined text-[18px]">upload_file</span>
                {t("Import PGN")}
              </Button>
            )}
          </div>
        }
      />

      {/* Search + player filters */}
      <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); load(1, opts); }}>
        <Input placeholder="Tìm theo tên, kỳ thủ, khai cuộc, sự kiện…" value={search}
          onChange={(e) => setSearch(e.target.value)} className="max-w-xs" />
        <Input placeholder="Trắng" value={white} onChange={(e) => setWhite(e.target.value)} className="max-w-[140px]" />
        <Input placeholder="Đen" value={black} onChange={(e) => setBlack(e.target.value)} className="max-w-[140px]" />
        <Button type="submit" variant="outline">{t("Search")}</Button>
      </form>

      {/* Filter row */}
      <div className="flex flex-wrap items-center gap-2">
        <FilterSelect value={result} onChange={setResult} placeholder="Kết quả" options={RESULTS} />
        {facets && facets.openings.length > 0 && (
          <FilterSelect value={opening} onChange={setOpening} placeholder="Khai cuộc"
            options={[{ value: "", label: "Mọi khai cuộc" }, ...facets.openings.map((o) => ({ value: o.value, label: `${o.value} (${o.count})` }))]} />
        )}
        {facets && facets.events.length > 0 && (
          <FilterSelect value={event} onChange={setEvent} placeholder="Sự kiện"
            options={[{ value: "", label: "Mọi sự kiện" }, ...facets.events.map((o) => ({ value: o.value, label: `${o.value} (${o.count})` }))]} />
        )}
        {facets && facets.sites.length > 0 && (
          <FilterSelect value={site} onChange={setSite} placeholder="Địa điểm"
            options={[{ value: "", label: "Mọi địa điểm" }, ...facets.sites.map((o) => ({ value: o.value, label: `${o.value} (${o.count})` }))]} />
        )}
        <FilterSelect value={eloBand} onChange={setEloBand} placeholder="ELO"
          options={Object.entries(ELO_BANDS).map(([value, b]) => ({ value, label: b.label }))} />
        <FilterSelect value={lengthBand} onChange={setLengthBand} placeholder="Độ dài"
          options={Object.entries(LENGTH_BANDS).map(([value, b]) => ({ value, label: b.label }))} />
        {facets && facets.sources.length > 0 && (
          <FilterSelect value={source} onChange={setSource} placeholder="Nguồn"
            options={[{ value: "", label: "Mọi nguồn" }, ...facets.sources.map((o) => ({ value: o.value, label: `${o.value} (${o.count})` }))]} />
        )}
        <FilterSelect value={analyzed} onChange={setAnalyzed} placeholder="Phân tích" options={ANALYZED} />
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <input type="checkbox" checked={named} onChange={(e) => setNamed(e.target.checked)} />
          Đã đặt tên
        </label>
        {canCoach && (
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <input type="checkbox" checked={draftsOnly} onChange={(e) => setDraftsOnly(e.target.checked)} />
            Chỉ bản nháp
          </label>
        )}
        <div className="ml-auto">
          <FilterSelect value={sort} onChange={setSort} placeholder="Sắp xếp" options={SORTS} />
        </div>
      </div>

      {/* Theme chips */}
      {facets && facets.themes.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {facets.themes.slice(0, 24).map((th) => {
            const on = activeThemes.includes(th.value);
            return (
              <button key={th.value} onClick={() => toggleTheme(th.value)}
                className={`rounded-full px-2.5 py-0.5 text-xs transition-colors ${on ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-muted/70"}`}>
                {th.value} <span className="opacity-60">{th.count}</span>
              </button>
            );
          })}
          {activeThemes.length > 0 && (
            <button onClick={() => setActiveThemes([])} className="text-xs text-primary hover:underline">Xoá lọc tag</button>
          )}
        </div>
      )}

      {/* Coach bulk-review toolbar */}
      {canCoach && games.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-black/10 bg-muted/40 px-3 py-2 text-sm">
          <span className="text-muted-foreground">Đã chọn {selected.size}</span>
          <button onClick={() => setSelected(new Set(games.map((g) => g.id)))} className="text-primary hover:underline">
            Chọn tất cả (trang này)
          </button>
          {selected.size > 0 && (
            <button onClick={() => setSelected(new Set())} className="text-muted-foreground hover:underline">Bỏ chọn</button>
          )}
          <div className="ml-auto flex gap-2">
            <Button size="sm" disabled={selected.size === 0 || bulkBusy} onClick={() => bulkPublish(true)}>Xuất bản đã chọn</Button>
            <Button size="sm" variant="outline" disabled={selected.size === 0 || bulkBusy} onClick={() => bulkPublish(false)}>Ẩn đã chọn</Button>
          </div>
        </div>
      )}

      {/* Results */}
      {loading ? (
        <p className="text-sm text-muted-foreground">Đang tải…</p>
      ) : games.length === 0 ? (
        <EmptyState icon="deployed_code" title={t("No games yet")}
          description="Đổi bộ lọc, hoặc nhập PGN để xây thư viện ván cờ." />
      ) : view === "grid" ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {games.map((g) => (
            <div key={g.id} className="relative rounded-lg border border-black/10 bg-card p-3">
              {canCoach && (
                <label className="absolute left-4 top-4 z-10 flex h-6 w-6 cursor-pointer items-center justify-center rounded bg-white/90 shadow-sm ring-1 ring-black/10">
                  <input type="checkbox" checked={selected.has(g.id)} onChange={() => toggleSelect(g.id)} aria-label="Chọn ván" />
                </label>
              )}
              <Link href={`/chess/games/${g.id}`}>
                <ChessBoard fen={g.final_fen || START_FEN} interactive={false} className="max-w-full" />
              </Link>
              <div className="mt-2 truncate text-sm font-medium">
                <Link href={`/chess/games/${g.id}`} className="hover:text-primary hover:underline">
                  {g.title || `${g.white || "?"} – ${g.black || "?"}`}
                </Link>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-1 text-[11px]">
                <span className="rounded bg-muted px-1.5 py-0.5 tabular-nums text-muted-foreground">{g.result || "*"}</span>
                {(g.white_elo || g.black_elo) && (
                  <span className="rounded bg-muted px-1.5 py-0.5 tabular-nums text-muted-foreground">
                    {g.white_elo || "?"}/{g.black_elo || "?"}
                  </span>
                )}
                <span className="rounded bg-muted px-1.5 py-0.5 tabular-nums text-muted-foreground">{Math.ceil(g.ply_count / 2)} nước</span>
                {g.played_year && <span className="rounded bg-muted px-1.5 py-0.5 text-muted-foreground">{g.played_year}</span>}
                {(g.brilliant_count ?? 0) > 0 && <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-emerald-800">!! {g.brilliant_count}</span>}
                {(g.blunder_count ?? 0) > 0 && <span className="rounded bg-red-100 px-1.5 py-0.5 text-red-800">?? {g.blunder_count}</span>}
                {!g.is_published && <span className="rounded bg-orange-100 px-1.5 py-0.5 text-orange-800">Nháp</span>}
              </div>
              {(g.eco || g.opening_name) && (
                <p className="mt-1 truncate text-[11px] text-muted-foreground">{g.eco ? `${g.eco} ` : ""}{g.opening_name || ""}</p>
              )}
              {canCoach && (
                <Button variant="outline" size="sm" className="mt-2 w-full" onClick={() => togglePublishOne(g)}>
                  {g.is_published ? "Ẩn (về nháp)" : "Xuất bản"}
                </Button>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-black/10">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-left text-muted-foreground">
              <tr>
                {canCoach && <th className="px-2 py-2" />}
                <th className="px-3 py-2 font-medium">{t("White")}</th>
                <th className="px-3 py-2 font-medium">{t("Black")}</th>
                <th className="px-3 py-2 font-medium">{t("Result")}</th>
                <th className="px-3 py-2 font-medium">{t("Opening")}</th>
                <th className="px-3 py-2 font-medium">{t("Date")}</th>
                <th className="px-3 py-2 font-medium">{t("Moves")}</th>
                {canCoach && <th className="px-3 py-2 font-medium" />}
              </tr>
            </thead>
            <tbody>
              {games.map((g) => (
                <tr key={g.id} className="border-t border-black/[0.06] hover:bg-muted/30">
                  {canCoach && (
                    <td className="px-2 py-2">
                      <input type="checkbox" checked={selected.has(g.id)} onChange={() => toggleSelect(g.id)} aria-label="Chọn ván" />
                    </td>
                  )}
                  <td className="cursor-pointer px-3 py-2" onClick={() => router.push(`/chess/games/${g.id}`)}>
                    {g.white || "—"}{g.white_elo ? ` (${g.white_elo})` : ""}
                    {!g.is_published && <span className="ml-1 rounded bg-orange-100 px-1 py-0.5 text-[10px] text-orange-800">Nháp</span>}
                  </td>
                  <td className="cursor-pointer px-3 py-2" onClick={() => router.push(`/chess/games/${g.id}`)}>{g.black || "—"}{g.black_elo ? ` (${g.black_elo})` : ""}</td>
                  <td className="px-3 py-2 tabular-nums">{g.result || "*"}</td>
                  <td className="px-3 py-2 text-muted-foreground">{g.eco ? `${g.eco} ` : ""}{g.opening_name || ""}</td>
                  <td className="px-3 py-2 text-muted-foreground">{g.played_at || "—"}</td>
                  <td className="px-3 py-2 tabular-nums text-muted-foreground">{Math.ceil(g.ply_count / 2)}</td>
                  {canCoach && (
                    <td className="px-3 py-2">
                      <Button variant="outline" size="sm" onClick={() => togglePublishOne(g)}>
                        {g.is_published ? "Ẩn" : "Xuất bản"}
                      </Button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => load(page - 1, opts)}>{t("Previous")}</Button>
          <span className="text-sm text-muted-foreground">Trang {page} / {totalPages}</span>
          <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => load(page + 1, opts)}>{t("Next")}</Button>
        </div>
      )}

      <Link href="/chess" className="text-sm text-muted-foreground hover:text-foreground">{t("Back to Chess")}</Link>
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
