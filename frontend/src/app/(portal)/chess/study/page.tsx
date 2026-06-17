"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { t } from "@/lib/i18n";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/empty-state";

type StudySet = {
  id: string;
  title: string;
  description?: string | null;
  kind: string;
  scope_type: string;
  created_at: string;
};

export default function ChessStudyPage() {
  const { hasPermission } = useAuth();
  const canCoach = hasPermission("chess:coach");
  const [sets, setSets] = useState<StudySet[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState("mixed");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api<{ items: StudySet[] }>("/api/chess/study-sets");
      setSets(data.items);
    } catch {
      setSets([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function create() {
    if (!title.trim()) return;
    setCreating(true);
    setError(null);
    try {
      await api("/api/chess/study-sets", {
        method: "POST",
        body: { title, kind, scope_type: "global" },
      });
      setTitle("");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to create study set");
    } finally {
      setCreating(false);
    }
  }

  return (
    <>
      <PageHeader title={t("Study sets")} description={t("Curated collections of games, puzzles and positions.")} />

      {canCoach && (
        <div className="flex flex-wrap items-end gap-2 rounded-lg border border-black/10 bg-card p-4">
          <div className="flex-1 min-w-[220px]">
            <label className="mb-1 block text-sm font-medium">New study set</label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Sicilian Najdorf essentials" />
          </div>
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value)}
            className="h-9 rounded-md border border-black/10 bg-background px-2 text-sm"
          >
            <option value="mixed">Mixed</option>
            <option value="opening">Opening</option>
            <option value="tactics">Tactics</option>
            <option value="endgame">Endgame</option>
          </select>
          <Button onClick={create} disabled={creating || !title.trim()}>Create</Button>
          {error && <p className="w-full text-sm text-destructive">{error}</p>}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : sets.length === 0 ? (
        <EmptyState icon="library_books" title="No study sets yet" description={canCoach ? "Create one above to start curating." : "A coach hasn't published any study sets yet."} />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {sets.map((s) => (
            <Link key={s.id} href={`/chess/study/${s.id}`} className="rounded-lg border border-black/10 bg-card p-4 hover:border-primary/40">
              <div className="flex items-center justify-between">
                <h3 className="font-heading text-lg">{s.title}</h3>
                <Badge variant="secondary">{s.kind}</Badge>
              </div>
              {s.description && <p className="mt-1 text-sm text-muted-foreground">{s.description}</p>}
            </Link>
          ))}
        </div>
      )}

      <Link href="/chess" className="text-sm text-muted-foreground hover:text-foreground">← Back to Chess</Link>
    </>
  );
}
