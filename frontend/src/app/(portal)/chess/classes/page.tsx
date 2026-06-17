"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/empty-state";

type ClassSummary = {
  id: string;
  name: string;
  description?: string | null;
  your_role?: string | null;
  student_count: number;
  created_at: string;
};

export default function ChessClassesPage() {
  const { hasPermission } = useAuth();
  const canCoach = hasPermission("chess:coach");
  const [classes, setClasses] = useState<ClassSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await api<{ items: ClassSummary[] }>("/api/chess/classes");
      setClasses(d.items);
    } catch {
      setClasses([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function create() {
    if (!name.trim()) return;
    setError(null);
    try {
      await api("/api/chess/classes", { method: "POST", body: { name } });
      setName("");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Tạo lớp thất bại");
    }
  }

  return (
    <>
      <PageHeader title="Lớp học" description="Quản lý lớp, bài giảng và bài giao cho học viên." />

      {canCoach && (
        <div className="flex flex-wrap items-end gap-2 rounded-lg border border-black/10 bg-card p-4">
          <div className="min-w-[240px] flex-1">
            <label className="mb-1 block text-sm font-medium">Tạo lớp mới</label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="VD: Lớp khai cuộc cơ bản" />
          </div>
          <Button onClick={create} disabled={!name.trim()}>Tạo lớp</Button>
          {error && <p className="w-full text-sm text-destructive">{error}</p>}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-muted-foreground">Đang tải…</p>
      ) : classes.length === 0 ? (
        <EmptyState icon="school" title="Chưa có lớp nào" description={canCoach ? "Tạo lớp ở trên để bắt đầu." : "Bạn chưa được thêm vào lớp nào."} />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {classes.map((c) => (
            <Link key={c.id} href={`/chess/classes/${c.id}`} className="rounded-lg border border-black/10 bg-card p-4 hover:border-primary/40">
              <div className="flex items-center justify-between">
                <h3 className="font-heading text-lg">{c.name}</h3>
                {c.your_role && <Badge variant="secondary">{c.your_role === "coach" ? "HLV" : c.your_role === "admin" ? "Admin" : "Học viên"}</Badge>}
              </div>
              {c.description && <p className="mt-1 text-sm text-muted-foreground">{c.description}</p>}
              <p className="mt-2 text-xs text-muted-foreground">{c.student_count} học viên</p>
            </Link>
          ))}
        </div>
      )}

      <Link href="/chess" className="text-sm text-muted-foreground hover:text-foreground">← Về Cờ vua</Link>
    </>
  );
}
