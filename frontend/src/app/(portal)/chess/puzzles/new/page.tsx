"use client";

import Link from "next/link";
import { Chess } from "chess.js";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ChessBoard, type BoardMove } from "@/components/chess/ChessBoard";

const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

type Step = { uci: string; san: string; fen: string };

export default function NewPuzzlePage() {
  const router = useRouter();
  const { hasPermission } = useAuth();
  const canCoach = hasPermission("chess:coach");

  const [startFen, setStartFen] = useState("");
  const [committedFen, setCommittedFen] = useState<string | null>(null);
  const [steps, setSteps] = useState<Step[]>([]);
  const [title, setTitle] = useState("");
  const [rating, setRating] = useState("");
  const [themes, setThemes] = useState("");
  const [description, setDescription] = useState("");
  const [published, setPublished] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const startValid = useMemo(() => {
    if (!startFen.trim()) return null;
    try {
      new Chess(startFen.trim());
      return true;
    } catch {
      return false;
    }
  }, [startFen]);

  // Current board position = last step's fen, or the committed start.
  const boardFen = steps.length ? steps[steps.length - 1].fen : committedFen ?? START_FEN;
  const lastMove = steps.length
    ? { from: steps[steps.length - 1].uci.slice(0, 2), to: steps[steps.length - 1].uci.slice(2, 4) }
    : null;

  function onMove(m: BoardMove) {
    setSteps((s) => [...s, { uci: `${m.from}${m.to}${m.promotion ?? ""}`, san: m.san, fen: m.fen }]);
  }

  async function save() {
    setError(null);
    if (!committedFen) {
      setError("Hãy nạp thế cờ bắt đầu (FEN) trước.");
      return;
    }
    if (steps.length === 0) {
      setError("Hãy đi ít nhất một nước để làm lời giải.");
      return;
    }
    setSaving(true);
    try {
      await api("/api/chess/puzzles", {
        method: "POST",
        body: {
          fen: committedFen,
          solution_moves: steps.map((s) => s.uci),
          themes: themes.split(",").map((t) => t.trim()).filter(Boolean),
          rating: rating ? Number(rating) : null,
          title: title || null,
          description: description || null,
          is_published: published,
        },
      });
      router.push("/chess/puzzles");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Lưu thất bại");
    } finally {
      setSaving(false);
    }
  }

  if (!canCoach) {
    return (
      <>
        <PageHeader title="Tạo bài tập" />
        <p className="text-sm text-muted-foreground">Bạn cần quyền HLV (chess:coach) để tạo bài tập.</p>
        <Link href="/chess/puzzles" className="text-sm text-primary hover:underline">← Về Bài tập</Link>
      </>
    );
  }

  return (
    <>
      <PageHeader title="Tạo bài tập" description="Nạp thế cờ rồi đi các nước để ghi lại lời giải." />

      {!committedFen ? (
        <div className="max-w-2xl space-y-3 rounded-lg border border-black/10 bg-card p-4">
          <label className="block text-sm font-medium">Thế cờ bắt đầu (FEN)</label>
          <Input value={startFen} onChange={(e) => setStartFen(e.target.value)} placeholder={START_FEN} className="font-mono text-xs" />
          {startFen.trim() && (
            <p className={`text-xs ${startValid ? "text-green-700" : "text-destructive"}`}>
              {startValid ? "FEN hợp lệ" : "FEN không hợp lệ"}
            </p>
          )}
          <div className="flex gap-2">
            <Button disabled={!startValid} onClick={() => { setCommittedFen(startFen.trim()); setSteps([]); }}>
              Nạp thế cờ
            </Button>
            <Button variant="outline" onClick={() => { setStartFen(START_FEN); }}>Thế cờ khởi đầu</Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-4 lg:flex-row">
          <div className="flex-1">
            <ChessBoard fen={boardFen} interactive onMove={onMove} lastMove={lastMove} />
            <div className="mt-3 flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setSteps((s) => s.slice(0, -1))} disabled={!steps.length}>
                Hoàn tác nước
              </Button>
              <Button variant="outline" size="sm" onClick={() => setSteps([])} disabled={!steps.length}>Xoá lời giải</Button>
              <Button variant="ghost" size="sm" onClick={() => { setCommittedFen(null); setSteps([]); }}>Đổi thế cờ</Button>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">
              Lời giải: {steps.length ? steps.map((s) => s.san).join(" ") : "(chưa có nước nào)"}
            </p>
          </div>

          <div className="w-full lg:w-72 shrink-0 space-y-3">
            <div>
              <label className="mb-1 block text-sm font-medium">Tiêu đề</label>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="VD: Chiếu hết hàng cuối" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Độ khó (rating)</label>
              <Input value={rating} onChange={(e) => setRating(e.target.value)} type="number" placeholder="800" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Chủ đề (phẩy)</label>
              <Input value={themes} onChange={(e) => setThemes(e.target.value)} placeholder="mateIn1, backRankMate" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Mô tả</label>
              <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={published} onChange={(e) => setPublished(e.target.checked)} />
              Xuất bản cho học viên
            </label>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button onClick={save} disabled={saving} className="w-full">{saving ? "Đang lưu…" : "Lưu bài tập"}</Button>
          </div>
        </div>
      )}

      <Link href="/chess/puzzles" className="text-sm text-muted-foreground hover:text-foreground">← Về Bài tập</Link>
    </>
  );
}
