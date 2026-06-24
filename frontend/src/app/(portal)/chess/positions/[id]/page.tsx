"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
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
import type { ChessPosition } from "@/types/chess";

export default function ChessPositionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { hasPermission } = useAuth();
  const canEdit = hasPermission("chess:edit:own_dept") || hasPermission("chess:edit:all");

  const [pos, setPos] = useState<ChessPosition | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [editing, setEditing] = useState(false);

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
      <PageHeader
        title={pos.label || "Thế cờ"}
        description={pos.description ?? undefined}
        action={
          canEdit && !editing ? (
            <Button variant="outline" onClick={() => setEditing(true)}>
              <span className="material-symbols-outlined text-[18px]">edit</span> Sửa
            </Button>
          ) : undefined
        }
      />

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
            {pos.source_puzzle_id && (
              <Link href={`/chess/puzzles/${pos.source_puzzle_id}`} className="text-primary hover:underline">
                Giải puzzle →
              </Link>
            )}
          </div>
        </div>

        <div className="space-y-4">
          {editing ? (
            <EditPanel pos={pos} onSaved={(p) => { setPos(p); setEditing(false); }} onCancel={() => setEditing(false)} />
          ) : (
            <>
              {/* Attribute chips */}
              <div className="flex flex-wrap gap-2 text-xs">
                {pos.difficulty != null && <Attr label="Độ khó" value={`★ ${pos.difficulty}`} />}
                {pos.piece_count != null && <Attr label="Số quân" value={String(pos.piece_count)} />}
                {pos.side_to_move && <Attr label="Lượt đi" value={pos.side_to_move === "w" ? "Trắng" : "Đen"} />}
                {pos.popularity != null && <Attr label="Phổ biến" value={String(pos.popularity)} />}
                {pos.opening_name && <Attr label="Khai cuộc" value={pos.opening_name} />}
                {pos.source && <Attr label="Nguồn" value={pos.source} />}
              </div>
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
            </>
          )}
        </div>
      </div>

      <ChessBacklinks type="position" id={pos.id} />

      <Link href="/chess/positions" className="mt-8 inline-block text-sm text-muted-foreground hover:text-foreground">
        ← Danh sách thế cờ
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
  pos, onSaved, onCancel,
}: {
  pos: ChessPosition; onSaved: (p: ChessPosition) => void; onCancel: () => void;
}) {
  const [label, setLabel] = useState(pos.label ?? "");
  const [description, setDescription] = useState(pos.description ?? "");
  const [themes, setThemes] = useState((pos.themes ?? []).join(", "));
  const [difficulty, setDifficulty] = useState(pos.difficulty != null ? String(pos.difficulty) : "");
  const [opening, setOpening] = useState(pos.opening_name ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const updated = await api<ChessPosition>(`/api/chess/positions/${pos.id}`, {
        method: "PATCH",
        body: {
          label: label || null,
          description: description || null,
          themes: themes.split(",").map((s) => s.trim()).filter(Boolean),
          difficulty: difficulty ? Number(difficulty) : null,
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
        <Input value={label} onChange={(e) => setLabel(e.target.value)} />
      </div>
      <div>
        <label className="mb-1 block text-sm font-medium">Tag (cách nhau bằng dấu phẩy)</label>
        <Input value={themes} onChange={(e) => setThemes(e.target.value)} placeholder="khai cuộc, chiến thuật, tàn cuộc" />
      </div>
      <div className="flex gap-2">
        <div className="w-32">
          <label className="mb-1 block text-sm font-medium">Độ khó</label>
          <Input value={difficulty} onChange={(e) => setDifficulty(e.target.value)} type="number" />
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
