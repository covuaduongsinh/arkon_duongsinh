"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { WikiInsertPicker } from "@/components/chess/wiki-insert-picker";

type Member = { employee_id: string; name: string; role: string };
type ClassDetail = {
  id: string;
  name: string;
  description?: string | null;
  your_role?: string | null;
  student_count: number;
  members: Member[];
};
type Progress = { solved: number; total: number; completed: boolean };
type Assignment = {
  id: string;
  title: string;
  description?: string | null;
  kind: string;
  puzzle_ids: string[];
  due_at?: string | null;
  progress?: Progress;
};
type ProgressRow = { employee_id: string; name: string; solved: number; total: number; completed: boolean };
type PuzzleOpt = { id: string; title?: string | null; rating?: number | null };

export default function ClassDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [cls, setCls] = useState<ClassDetail | null>(null);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [lessons, setLessons] = useState<{ id: string; title: string }[]>([]);
  const [loading, setLoading] = useState(true);

  // roster
  const [email, setEmail] = useState("");
  // assignment creation
  const [aTitle, setATitle] = useState("");
  const [aDue, setADue] = useState("");
  const [puzzles, setPuzzles] = useState<PuzzleOpt[]>([]);
  const [selPuzzles, setSelPuzzles] = useState<Set<string>>(new Set());
  // lesson creation
  const [lTitle, setLTitle] = useState("");
  const [lContent, setLContent] = useState("");
  const [wikiPickerOpen, setWikiPickerOpen] = useState(false);
  // assignment progress popover
  const [progRows, setProgRows] = useState<Record<string, ProgressRow[]>>({});
  const [error, setError] = useState<string | null>(null);

  const canManage = cls?.your_role === "coach" || cls?.your_role === "admin";

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const [c, a, l] = await Promise.all([
        api<ClassDetail>(`/api/chess/classes/${id}`),
        api<{ items: Assignment[] }>(`/api/chess/classes/${id}/assignments`),
        api<{ items: { id: string; title: string }[] }>(`/api/chess/classes/${id}/lessons`),
      ]);
      setCls(c);
      setAssignments(a.items);
      setLessons(l.items);
    } catch {
      setCls(null);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  // Load published puzzles for the assignment builder (coach only).
  useEffect(() => {
    if (!canManage) return;
    api<{ items: PuzzleOpt[] }>("/api/chess/puzzles?page_size=100").then((d) => setPuzzles(d.items)).catch(() => setPuzzles([]));
  }, [canManage]);

  async function addMember() {
    if (!email.trim()) return;
    setError(null);
    try {
      await api(`/api/chess/classes/${id}/members`, { method: "POST", body: { email, role: "student" } });
      setEmail("");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Thêm học viên thất bại");
    }
  }

  async function removeMember(empId: string) {
    await api(`/api/chess/classes/${id}/members/${empId}`, { method: "DELETE" });
    await load();
  }

  async function createAssignment() {
    if (!aTitle.trim() || selPuzzles.size === 0) {
      setError("Cần tiêu đề và ít nhất 1 bài tập.");
      return;
    }
    setError(null);
    try {
      await api(`/api/chess/classes/${id}/assignments`, {
        method: "POST",
        body: {
          title: aTitle, kind: "puzzles", puzzle_ids: [...selPuzzles],
          due_at: aDue ? new Date(aDue).toISOString() : null,
        },
      });
      setATitle("");
      setADue("");
      setSelPuzzles(new Set());
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Tạo bài giao thất bại");
    }
  }

  async function loadProgress(assignmentId: string) {
    const d = await api<{ rows: ProgressRow[] }>(`/api/chess/assignments/${assignmentId}/progress`);
    setProgRows((p) => ({ ...p, [assignmentId]: d.rows }));
  }

  async function createLesson() {
    if (!lTitle.trim()) return;
    await api(`/api/chess/classes/${id}/lessons`, { method: "POST", body: { title: lTitle, content_md: lContent } });
    setLTitle("");
    setLContent("");
    await load();
  }

  async function deleteClass() {
    if (!confirm("Xoá lớp này?")) return;
    await api(`/api/chess/classes/${id}`, { method: "DELETE" });
    router.push("/chess/classes");
  }

  if (loading) return <p className="text-sm text-muted-foreground">Đang tải…</p>;
  if (!cls) return <p className="text-sm text-muted-foreground">Không tìm thấy lớp.</p>;

  return (
    <>
      <PageHeader
        title={cls.name}
        description={cls.description || undefined}
        action={
          <div className="flex items-center gap-2">
            <Badge variant="secondary">{cls.your_role === "coach" ? "HLV" : cls.your_role === "admin" ? "Admin" : "Học viên"}</Badge>
            {canManage && <Button variant="outline" size="sm" onClick={deleteClass}>Xoá lớp</Button>}
          </div>
        }
      />
      {error && <p className="text-sm text-destructive">{error}</p>}

      {/* Roster */}
      <section className="rounded-lg border border-black/10 bg-card p-4">
        <h3 className="mb-2 font-heading text-lg">Danh sách lớp</h3>
        {canManage && (
          <div className="mb-3 flex gap-2">
            <Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email học viên để thêm" className="max-w-xs" />
            <Button size="sm" onClick={addMember} disabled={!email.trim()}>Thêm</Button>
          </div>
        )}
        <div className="divide-y divide-black/[0.06]">
          {cls.members.map((m) => (
            <div key={m.employee_id} className="flex items-center justify-between py-1.5 text-sm">
              <span>{m.name} {m.role === "coach" && <Badge variant="outline" className="ml-1 text-[10px]">HLV</Badge>}</span>
              {canManage && m.role !== "coach" && (
                <button onClick={() => removeMember(m.employee_id)} className="text-xs text-destructive hover:underline">Xoá</button>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Assignments */}
      <section className="rounded-lg border border-black/10 bg-card p-4">
        <h3 className="mb-2 font-heading text-lg">Bài giao</h3>
        {canManage && (
          <div className="mb-3 space-y-2 rounded-md border border-black/10 p-3">
            <div className="flex flex-wrap gap-2">
              <Input value={aTitle} onChange={(e) => setATitle(e.target.value)} placeholder="Tiêu đề bài giao" className="min-w-[200px] flex-1" />
              <Input type="date" value={aDue} onChange={(e) => setADue(e.target.value)} className="w-40" />
              <Button size="sm" onClick={createAssignment} disabled={!aTitle.trim() || selPuzzles.size === 0}>Giao bài</Button>
            </div>
            <div className="max-h-40 overflow-y-auto rounded border border-black/10 p-2">
              {puzzles.length === 0 ? (
                <p className="text-xs text-muted-foreground">Chưa có bài tập đã xuất bản để giao.</p>
              ) : (
                puzzles.map((p) => (
                  <label key={p.id} className="flex items-center gap-2 py-0.5 text-sm">
                    <input
                      type="checkbox"
                      checked={selPuzzles.has(p.id)}
                      onChange={(e) => {
                        const next = new Set(selPuzzles);
                        if (e.target.checked) next.add(p.id); else next.delete(p.id);
                        setSelPuzzles(next);
                      }}
                    />
                    {p.title || "Bài tập"}{p.rating ? ` (${p.rating})` : ""}
                  </label>
                ))
              )}
            </div>
            <p className="text-xs text-muted-foreground">Đã chọn {selPuzzles.size} bài tập.</p>
          </div>
        )}

        {assignments.length === 0 ? (
          <p className="text-sm text-muted-foreground">Chưa có bài giao.</p>
        ) : (
          <div className="space-y-2">
            {assignments.map((a) => (
              <div key={a.id} className="rounded-md border border-black/[0.08] p-3">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="font-medium">{a.title}</span>
                    <span className="ml-2 text-xs text-muted-foreground">{a.puzzle_ids.length} bài tập{a.due_at ? ` · hạn ${new Date(a.due_at).toLocaleDateString("vi-VN")}` : ""}</span>
                  </div>
                  {a.progress ? (
                    <Badge variant={a.progress.completed ? "default" : "secondary"}>
                      {a.progress.solved}/{a.progress.total}{a.progress.completed ? " ✓" : ""}
                    </Badge>
                  ) : canManage ? (
                    <Button size="sm" variant="outline" onClick={() => loadProgress(a.id)}>Tiến độ</Button>
                  ) : null}
                </div>
                {progRows[a.id] && (
                  <div className="mt-2 border-t border-black/[0.06] pt-2 text-sm">
                    {progRows[a.id].length === 0 ? (
                      <p className="text-xs text-muted-foreground">Chưa có học viên.</p>
                    ) : (
                      progRows[a.id].map((r) => (
                        <div key={r.employee_id} className="flex items-center justify-between py-0.5">
                          <span>{r.name}</span>
                          <span className={`tabular-nums ${r.completed ? "text-green-700" : "text-muted-foreground"}`}>
                            {r.solved}/{r.total}{r.completed ? " ✓" : ""}
                          </span>
                        </div>
                      ))
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Lessons */}
      <section className="rounded-lg border border-black/10 bg-card p-4">
        <h3 className="mb-2 font-heading text-lg">Bài giảng</h3>
        {canManage && (
          <div className="mb-3 space-y-2 rounded-md border border-black/10 p-3">
            <Input value={lTitle} onChange={(e) => setLTitle(e.target.value)} placeholder="Tiêu đề bài giảng" />
            <Textarea value={lContent} onChange={(e) => setLContent(e.target.value)} rows={4} placeholder="Nội dung (Markdown, có thể nhúng ```pgn / ```fen)" className="font-mono text-xs" />
            <div className="flex gap-2">
              <Button size="sm" onClick={createLesson} disabled={!lTitle.trim()}>Thêm bài giảng</Button>
              <Button size="sm" variant="outline" onClick={() => setWikiPickerOpen(true)} className="gap-1.5">
                <span className="material-symbols-outlined text-sm">menu_book</span>
                Chèn từ Wiki
              </Button>
            </div>
          </div>
        )}
        {lessons.length === 0 ? (
          <p className="text-sm text-muted-foreground">Chưa có bài giảng.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {lessons.map((l) => (
              <li key={l.id}>
                <Link href={`/chess/lessons/${l.id}`} className="text-primary hover:underline">{l.title}</Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <Link href="/chess/classes" className="text-sm text-muted-foreground hover:text-foreground">← Về Lớp học</Link>

      <WikiInsertPicker
        open={wikiPickerOpen}
        onOpenChange={setWikiPickerOpen}
        onInsert={(md) => setLContent((prev) => (prev ? `${prev.replace(/\s+$/, "")}\n${md}` : md.replace(/^\s+/, "")))}
      />
    </>
  );
}
