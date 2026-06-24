"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ChessBoard } from "@/components/chess/ChessBoard";
import { ChessBacklinks } from "@/components/chess/ChessBacklinks";
import { WikilinkTokens } from "@/components/chess/WikilinkTokens";
import { PuzzleTrainer } from "@/components/chess/PuzzleTrainer";
import type { ChessPuzzle } from "@/types/chess";

export default function ChessPuzzleDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { hasPermission } = useAuth();
  const canEdit = hasPermission("chess:edit:own_dept") || hasPermission("chess:edit:all");
  const canCoach = hasPermission("chess:coach");
  const canDelete = hasPermission("chess:delete:own_dept") || hasPermission("chess:delete:all");

  const [puzzle, setPuzzle] = useState<ChessPuzzle | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [solving, setSolving] = useState(false);
  const [editing, setEditing] = useState(false);

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

  async function togglePublish() {
    if (!puzzle) return;
    const updated = await api<ChessPuzzle>(`/api/chess/puzzles/${puzzle.id}`, {
      method: "PATCH",
      body: { is_published: !puzzle.is_published },
    });
    setPuzzle(updated);
  }

  async function remove() {
    if (!puzzle || !confirm("Xoá bài tập này?")) return;
    await api(`/api/chess/puzzles/${puzzle.id}`, { method: "DELETE" });
    router.push("/chess/puzzles");
  }

  if (loading) return <p className="text-sm text-muted-foreground">Đang tải…</p>;
  if (notFound || !puzzle)
    return (
      <>
        <PageHeader title="Không tìm thấy bài tập" />
        <Link href="/chess/puzzles" className="text-sm text-primary hover:underline">
          ← Thư viện bài tập
        </Link>
      </>
    );

  return (
    <>
      <PageHeader
        title={puzzle.title || "Bài tập"}
        description={puzzle.description ?? undefined}
        action={
          <div className="flex flex-wrap gap-2">
            {canCoach && (
              <Button variant="outline" onClick={togglePublish}>
                {puzzle.is_published ? "Ẩn (về nháp)" : "Xuất bản"}
              </Button>
            )}
            {canEdit && !editing && (
              <Button variant="outline" onClick={() => setEditing(true)}>
                <span className="material-symbols-outlined text-[18px]">edit</span> Sửa
              </Button>
            )}
            {canDelete && (
              <Button variant="outline" onClick={remove}>
                <span className="material-symbols-outlined text-[18px]">delete</span> Xoá
              </Button>
            )}
          </div>
        }
      />

      {solving ? (
        <PuzzleTrainer puzzle={puzzle} onNext={() => setSolving(false)} />
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,420px)_1fr]">
          <div>
            <ChessBoard
              fen={puzzle.fen}
              orientation={puzzle.side_to_move === "b" ? "black" : "white"}
              interactive={false}
              className="max-w-[400px]"
            />
            <div className="mt-3 flex flex-wrap gap-3 text-sm">
              <button onClick={() => setSolving(true)} className="font-medium text-primary hover:underline">
                Giải bài này →
              </button>
              <Link href="/chess/puzzles/train" className="text-muted-foreground hover:text-foreground">
                Luyện tập ngẫu nhiên →
              </Link>
            </div>
          </div>

          <div className="space-y-4">
            {editing ? (
              <EditPanel puzzle={puzzle} onSaved={(p) => { setPuzzle(p); setEditing(false); }} onCancel={() => setEditing(false)} />
            ) : (
              <>
                <div className="flex flex-wrap gap-2 text-xs">
                  <Attr label="Lượt đi" value={puzzle.side_to_move === "b" ? "Đen" : "Trắng"} />
                  {puzzle.rating != null && <Attr label="Độ khó" value={`★ ${puzzle.rating}`} />}
                  {puzzle.piece_count != null && <Attr label="Số quân" value={String(puzzle.piece_count)} />}
                  {puzzle.popularity != null && <Attr label="Phổ biến" value={String(puzzle.popularity)} />}
                  {puzzle.opening_name && <Attr label="Khai cuộc" value={puzzle.opening_name} />}
                  {puzzle.source && <Attr label="Nguồn" value={puzzle.source} />}
                  <Attr label="Trạng thái" value={puzzle.is_published ? "Đã xuất bản" : "Nháp"} />
                </div>
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
              </>
            )}
          </div>
        </div>
      )}

      <ChessBacklinks type="puzzle" id={puzzle.id} />

      <Link href="/chess/puzzles" className="mt-8 inline-block text-sm text-muted-foreground hover:text-foreground">
        ← Thư viện bài tập
      </Link>
    </>
  );
}

function Attr({ label, value }: { label: string; value: string }) {
  return (
    <span className="rounded-md bg-muted px-2 py-1 text-muted-foreground">
      <span className="opacity-60">{label}:</span> {value}
    </span>
  );
}

function EditPanel({
  puzzle, onSaved, onCancel,
}: {
  puzzle: ChessPuzzle; onSaved: (p: ChessPuzzle) => void; onCancel: () => void;
}) {
  const [title, setTitle] = useState(puzzle.title ?? "");
  const [description, setDescription] = useState(puzzle.description ?? "");
  const [themes, setThemes] = useState((puzzle.themes ?? []).join(", "));
  const [rating, setRating] = useState(puzzle.rating != null ? String(puzzle.rating) : "");
  const [opening, setOpening] = useState(puzzle.opening_name ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const updated = await api<ChessPuzzle>(`/api/chess/puzzles/${puzzle.id}`, {
        method: "PATCH",
        body: {
          title: title || null,
          description: description || null,
          themes: themes.split(",").map((s) => s.trim()).filter(Boolean),
          rating: rating ? Number(rating) : null,
          opening_name: opening || null,
        },
      });
      onSaved(updated);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không lưu được thay đổi");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-2 rounded-lg border border-black/10 bg-card p-4">
      <div>
        <label className="mb-1 block text-sm font-medium">Tên</label>
        <Input value={title} onChange={(e) => setTitle(e.target.value)} />
      </div>
      <div>
        <label className="mb-1 block text-sm font-medium">Tag (cách nhau bằng dấu phẩy)</label>
        <Input value={themes} onChange={(e) => setThemes(e.target.value)} placeholder="fork, mateIn2, endgame" />
      </div>
      <div className="flex gap-2">
        <div className="w-32">
          <label className="mb-1 block text-sm font-medium">Độ khó</label>
          <Input value={rating} onChange={(e) => setRating(e.target.value)} type="number" />
        </div>
        <div className="flex-1">
          <label className="mb-1 block text-sm font-medium">Khai cuộc</label>
          <Input value={opening} onChange={(e) => setOpening(e.target.value)} />
        </div>
      </div>
      <div>
        <label className="mb-1 block text-sm font-medium">Mô tả</label>
        <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <div className="flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={onCancel}>Huỷ</Button>
        <Button size="sm" onClick={save} disabled={saving}>Lưu</Button>
      </div>
    </div>
  );
}
