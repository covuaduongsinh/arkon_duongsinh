"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, apiUpload, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { PuzzleImportJob } from "@/types/chess";

const OFFICIAL_URL = "https://database.lichess.org/lichess_db_puzzle.csv.zst";
const MAX_LIMIT = 50000;

function isTerminal(s?: PuzzleImportJob["status"]): boolean {
  return s === "completed" || s === "failed" || s === "cancelled";
}

export default function PuzzleImportPage() {
  const { hasPermission } = useAuth();
  const canCoach = hasPermission("chess:coach");

  const [mode, setMode] = useState<"url" | "upload">("url");
  const [url, setUrl] = useState(OFFICIAL_URL);
  const fileRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState<string | null>(null);

  const [minRating, setMinRating] = useState("");
  const [maxRating, setMaxRating] = useState("");
  const [theme, setTheme] = useState("");
  const [opening, setOpening] = useState("");
  const [limit, setLimit] = useState("5000");
  const [publish, setPublish] = useState(false);
  const [sync, setSync] = useState(true);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<PuzzleImportJob | null>(null);

  // Poll the running job until it reaches a terminal state.
  useEffect(() => {
    if (!job || isTerminal(job.status)) return;
    const id = setInterval(async () => {
      try {
        const fresh = await api<PuzzleImportJob>(`/api/chess/puzzles/import/${job.id}`);
        setJob(fresh);
      } catch {
        /* keep last state on transient poll errors */
      }
    }, 1500);
    return () => clearInterval(id);
  }, [job]);

  if (!canCoach) {
    return (
      <>
        <PageHeader title="Nhập bài tập từ Lichess" />
        <p className="text-sm text-destructive">
          Bạn cần quyền huấn luyện viên (chess:coach) để nhập bài tập.
        </p>
        <Link href="/chess/puzzles" className="text-sm text-primary hover:underline">← Về thư viện bài tập</Link>
      </>
    );
  }

  async function submit() {
    setError(null);
    const lim = limit.trim();
    const hasFilter = !!(minRating || maxRating || theme.trim() || opening.trim());
    if (!lim && !hasFilter) {
      setError("Cần ít nhất một bộ lọc (rating / theme / khai cuộc) hoặc giới hạn số bài.");
      return;
    }
    if (lim && (Number(lim) <= 0 || Number(lim) > MAX_LIMIT)) {
      setError(`Giới hạn phải từ 1 đến ${MAX_LIMIT.toLocaleString()}.`);
      return;
    }

    const form = new FormData();
    form.append("mode", mode);
    if (mode === "url") {
      form.append("url", url.trim() || OFFICIAL_URL);
    } else {
      const f = fileRef.current?.files?.[0];
      if (!f) {
        setError("Chọn một tệp .csv hoặc .csv.zst để tải lên.");
        return;
      }
      form.append("file", f);
    }
    if (minRating) form.append("min_rating", minRating);
    if (maxRating) form.append("max_rating", maxRating);
    if (theme.trim()) form.append("theme", theme.trim());
    if (opening.trim()) form.append("opening", opening.trim());
    if (lim) form.append("limit", lim);
    form.append("publish", publish ? "true" : "false");
    form.append("sync", sync ? "true" : "false");

    setBusy(true);
    try {
      // Long timeout — an uploaded file is streamed to the server before we get the job back.
      const created = await apiUpload<PuzzleImportJob>("/api/chess/puzzles/import", form, 600_000);
      setJob(created);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Khởi tạo nhập thất bại");
    } finally {
      setBusy(false);
    }
  }

  const running = job && !isTerminal(job.status);

  return (
    <>
      <PageHeader
        title="Nhập bài tập từ Lichess"
        description="Tải kho bài tập Lichess (CSV / .zst) vào thư viện. Chạy nền — bạn có thể rời trang."
      />

      <div className="max-w-2xl space-y-5">
        {/* Source mode toggle */}
        <div className="inline-flex rounded-md border border-black/10 p-0.5">
          <button
            type="button"
            onClick={() => setMode("url")}
            className={`rounded px-3 py-1.5 text-sm ${mode === "url" ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}
          >
            Tải từ Lichess (URL)
          </button>
          <button
            type="button"
            onClick={() => setMode("upload")}
            className={`rounded px-3 py-1.5 text-sm ${mode === "upload" ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}
          >
            Tải tệp lên
          </button>
        </div>

        {mode === "url" ? (
          <div>
            <label className="mb-1 block text-sm font-medium">URL kho bài tập</label>
            <Input value={url} onChange={(e) => setUrl(e.target.value)} className="font-mono text-xs" />
            <p className="mt-1 text-xs text-muted-foreground">
              Mặc định là kho chính thức của Lichess (~280MB .zst, ~5 triệu bài). Server cần truy cập internet.
            </p>
          </div>
        ) : (
          <div>
            <label className="mb-1 block text-sm font-medium">Tệp CSV / .zst</label>
            <input
              ref={fileRef}
              type="file"
              accept=".csv,.zst"
              onChange={(e) => setFileName(e.target.files?.[0]?.name ?? null)}
              className="block w-full text-sm file:mr-3 file:rounded-md file:border file:border-black/10 file:bg-muted file:px-3 file:py-1.5 file:text-sm"
            />
            {fileName && <p className="mt-1 text-xs text-muted-foreground">{fileName}</p>}
          </div>
        )}

        {/* Filters */}
        <div className="grid grid-cols-2 gap-3">
          <Field label="Rating tối thiểu">
            <Input type="number" value={minRating} onChange={(e) => setMinRating(e.target.value)} placeholder="vd 1200" />
          </Field>
          <Field label="Rating tối đa">
            <Input type="number" value={maxRating} onChange={(e) => setMaxRating(e.target.value)} placeholder="vd 2200" />
          </Field>
          <Field label="Theme (chứa)">
            <Input value={theme} onChange={(e) => setTheme(e.target.value)} placeholder="vd fork, endgame" />
          </Field>
          <Field label="Khai cuộc (chứa)">
            <Input value={opening} onChange={(e) => setOpening(e.target.value)} placeholder="vd Sicilian" />
          </Field>
          <Field label={`Giới hạn số bài (tối đa ${MAX_LIMIT.toLocaleString()})`}>
            <Input type="number" value={limit} onChange={(e) => setLimit(e.target.value)} placeholder="vd 5000" />
          </Field>
        </div>

        <div className="space-y-2">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={publish} onChange={(e) => setPublish(e.target.checked)} />
            Xuất bản ngay (học viên thấy ngay). Bỏ chọn = nhập dạng bản nháp để duyệt.
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={sync} onChange={(e) => setSync(e.target.checked)} />
            Đồng bộ vào Thư viện thế cờ sau khi nhập.
          </label>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="flex gap-2">
          <Button onClick={submit} disabled={busy || !!running}>
            {busy ? "Đang gửi…" : running ? "Đang chạy…" : "Bắt đầu nhập"}
          </Button>
          <Link href="/chess/puzzles">
            <Button variant="outline">Về thư viện</Button>
          </Link>
        </div>

        {/* Progress / result panel */}
        {job && (
          <div className="rounded-lg border border-black/10 bg-card p-4 text-sm">
            <div className="flex items-center gap-2">
              <StatusBadge status={job.status} />
              {running && <span className="text-muted-foreground">Đang xử lý nền…</span>}
            </div>
            <div className="mt-3 grid grid-cols-3 gap-3 text-center">
              <Stat label="Đã đọc" value={job.rows_read} />
              <Stat label="Đã thêm" value={job.inserted} />
              <Stat label="Trùng (bỏ qua)" value={job.skipped} />
            </div>
            {job.positions_synced > 0 && (
              <p className="mt-2 text-xs text-muted-foreground">
                Đã đồng bộ {job.positions_synced} thế cờ mới vào thư viện thế cờ.
              </p>
            )}
            {job.status === "failed" && job.error_message && (
              <p className="mt-2 text-xs text-destructive">Lỗi: {job.error_message}</p>
            )}
            {job.status === "completed" && (
              <p className="mt-3 text-xs text-muted-foreground">
                Hoàn tất. {publish ? "Bài tập đã xuất bản." : "Bài tập đang ở dạng bản nháp — mở thư viện, bật “Hiện bản nháp” và chọn nguồn Lichess để xem."}{" "}
                <Link href="/chess/puzzles" className="text-primary hover:underline">Mở thư viện →</Link>
              </p>
            )}
          </div>
        )}
      </div>
    </>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-muted-foreground">{label}</label>
      {children}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md bg-muted/50 py-2">
      <div className="text-lg font-semibold tabular-nums">{value.toLocaleString()}</div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
    </div>
  );
}

function StatusBadge({ status }: { status: PuzzleImportJob["status"] }) {
  const map: Record<PuzzleImportJob["status"], { label: string; cls: string }> = {
    pending: { label: "Đang chờ", cls: "bg-muted text-muted-foreground" },
    running: { label: "Đang chạy", cls: "bg-blue-100 text-blue-800" },
    completed: { label: "Hoàn tất", cls: "bg-green-100 text-green-800" },
    failed: { label: "Thất bại", cls: "bg-red-100 text-red-800" },
    cancelled: { label: "Đã huỷ", cls: "bg-muted text-muted-foreground" },
  };
  const s = map[status];
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${s.cls}`}>{s.label}</span>;
}
