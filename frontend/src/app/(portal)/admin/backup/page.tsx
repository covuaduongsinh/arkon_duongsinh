"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { apiUpload } from "@/lib/api";
import { PageHeader } from "@/components/shared/page-header";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL !== undefined
    ? process.env.NEXT_PUBLIC_API_URL
    : "http://localhost:5055";

const SECTIONS = [
  { key: "wiki", label: "Wiki (pages, history, drafts)" },
  { key: "sources", label: "Documents / Sources + original files" },
  { key: "skills", label: "AI Skills" },
  { key: "config", label: "Config & RBAC (departments, employees, settings)" },
] as const;

type SectionKey = (typeof SECTIONS)[number]["key"];

type TableCounts = { add: number; update: number; conflict: number; total: number };
type ImportReport = {
  mode: string;
  dry_run: boolean;
  bundle?: { arkon_version?: string; created_at?: string; include_files?: boolean };
  sections: Record<string, Record<string, TableCounts>>;
  files_uploaded?: number;
};

function token(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("arkon_token");
}

async function downloadFile(path: string, fallbackName: string) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { ...(token() ? { Authorization: `Bearer ${token()}` } : {}) },
  });
  if (!res.ok) {
    let detail = `Error ${res.status}`;
    try {
      detail = (await res.json())?.detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const name = match ? match[1] : fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

function sumSection(tables: Record<string, TableCounts>): TableCounts {
  return Object.values(tables).reduce(
    (acc, t) => ({
      add: acc.add + t.add,
      update: acc.update + t.update,
      conflict: acc.conflict + t.conflict,
      total: acc.total + t.total,
    }),
    { add: 0, update: 0, conflict: 0, total: 0 },
  );
}

export default function BackupPage() {
  const { user } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (user && user.role !== "admin") router.replace("/");
  }, [user, router]);

  if (!user || user.role !== "admin") {
    return (
      <div className="flex items-center justify-center py-16">
        <span className="material-symbols-outlined text-3xl text-muted-foreground animate-spin">
          progress_activity
        </span>
      </div>
    );
  }

  return (
    <>
      <PageHeader
        title="Backup & Restore"
        description="Export and import a portable data bundle, or take a full disaster-recovery snapshot."
      />
      <div className="flex flex-col gap-6">
        <ExportCard />
        <ImportCard />
        <SnapshotCard />
      </div>
    </>
  );
}

/* ─── Export ─── */

function ExportCard() {
  const [selected, setSelected] = useState<Record<SectionKey, boolean>>({
    wiki: true,
    sources: true,
    skills: true,
    config: true,
  });
  const [includeFiles, setIncludeFiles] = useState(true);
  const [includeSecrets, setIncludeSecrets] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const chosen = SECTIONS.filter((s) => selected[s.key]).map((s) => s.key);

  const onExport = async () => {
    setBusy(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        sections: chosen.join(","),
        include_files: String(includeFiles),
        include_secrets: String(includeSecrets),
      });
      await downloadFile(`/api/admin/backup/export?${params}`, "arkon_backup.arkon.zip");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span className="material-symbols-outlined text-lg">cloud_download</span>
          Export bundle
        </CardTitle>
        <CardDescription>
          Download a portable <code>.arkon.zip</code> you can re-import here or into another Arkon
          instance. Embeddings are excluded (re-generate after import).
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid gap-2 sm:grid-cols-2">
          {SECTIONS.map((s) => (
            <label key={s.key} className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={selected[s.key]}
                onCheckedChange={(c) => setSelected((p) => ({ ...p, [s.key]: c }))}
              />
              {s.label}
            </label>
          ))}
        </div>

        <div className="flex flex-col gap-2 border-t pt-3">
          <label className="flex items-center gap-2 text-sm">
            <Checkbox checked={includeFiles} onCheckedChange={setIncludeFiles} />
            Include original files (documents, images, skill packages)
          </label>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox checked={includeSecrets} onCheckedChange={setIncludeSecrets} />
            <span className="text-amber-600 dark:text-amber-400">
              Include secrets (API keys, SMTP/webhook credentials) — only restorable on the same
              server
            </span>
          </label>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div>
          <Button onClick={onExport} disabled={busy || chosen.length === 0}>
            {busy ? (
              <span className="material-symbols-outlined animate-spin">progress_activity</span>
            ) : (
              <span className="material-symbols-outlined">download</span>
            )}
            Create &amp; download backup
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

/* ─── Import ─── */

function ImportCard() {
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<"merge" | "replace">("merge");
  const [report, setReport] = useState<ImportReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const run = async (dryRun: boolean) => {
    if (!file) return;
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("mode", mode);
      fd.append("dry_run", String(dryRun));
      const res = await apiUpload<ImportReport>("/api/admin/backup/import", fd, 600_000);
      setReport(res);
      if (!dryRun) {
        setDone(
          `Import complete (${mode}). Files restored: ${res.files_uploaded ?? 0}. ` +
            `Re-run embeddings from Settings to make new content searchable.`,
        );
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setBusy(false);
    }
  };

  const onRestore = async () => {
    const ok = window.confirm(
      mode === "replace"
        ? "REPLACE will delete existing rows in the selected sections before importing. Continue?"
        : "Merge will add new rows and update matching ones. Continue?",
    );
    if (ok) await run(false);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span className="material-symbols-outlined text-lg">upload</span>
          Import / restore bundle
        </CardTitle>
        <CardDescription>
          Upload a <code>.arkon.zip</code>, analyze the changes, then choose how to apply them.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="bundle-file">Bundle file</Label>
          <Input
            id="bundle-file"
            type="file"
            accept=".zip,.arkon.zip"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setReport(null);
              setDone(null);
            }}
          />
        </div>

        <div className="flex flex-col gap-2">
          <span className="text-sm font-medium">Apply mode</span>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name="mode"
              checked={mode === "merge"}
              onChange={() => setMode("merge")}
            />
            <span>
              <strong>Merge</strong> — add new + update matching (safe)
            </span>
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name="mode"
              checked={mode === "replace"}
              onChange={() => setMode("replace")}
            />
            <span className="text-destructive">
              <strong>Replace</strong> — wipe selected sections, then import
            </span>
          </label>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}
        {done && <p className="text-sm text-green-600 dark:text-green-400">{done}</p>}

        {report && <ReportTable report={report} />}

        <div className="flex gap-2">
          <Button variant="outline" onClick={() => run(true)} disabled={!file || busy}>
            {busy ? (
              <span className="material-symbols-outlined animate-spin">progress_activity</span>
            ) : (
              <span className="material-symbols-outlined">search</span>
            )}
            Analyze
          </Button>
          <Button onClick={onRestore} disabled={!file || busy}>
            <span className="material-symbols-outlined">restore</span>
            Restore
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function ReportTable({ report }: { report: ImportReport }) {
  const entries = Object.entries(report.sections);
  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">No matching sections in this bundle.</p>;
  }
  return (
    <div className="rounded-lg border">
      <table className="w-full text-sm">
        <thead className="border-b bg-muted/40 text-left text-xs uppercase text-muted-foreground">
          <tr>
            <th className="px-3 py-2">Section</th>
            <th className="px-3 py-2 text-right">Add</th>
            <th className="px-3 py-2 text-right">Update</th>
            <th className="px-3 py-2 text-right">Conflict</th>
            <th className="px-3 py-2 text-right">Total</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([section, tables]) => {
            const s = sumSection(tables);
            return (
              <tr key={section} className="border-b last:border-0">
                <td className="px-3 py-2 font-medium capitalize">{section}</td>
                <td className="px-3 py-2 text-right text-green-600 dark:text-green-400">{s.add}</td>
                <td className="px-3 py-2 text-right text-blue-600 dark:text-blue-400">{s.update}</td>
                <td className="px-3 py-2 text-right text-amber-600 dark:text-amber-400">
                  {s.conflict}
                </td>
                <td className="px-3 py-2 text-right text-muted-foreground">{s.total}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {report.dry_run && (
        <p className="px-3 py-2 text-xs text-muted-foreground">
          Preview only — nothing has been written yet. Click Restore to apply.
        </p>
      )}
    </div>
  );
}

/* ─── Snapshot ─── */

function SnapshotCard() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState<string | null>(null);

  const onDownload = async () => {
    setBusy(true);
    setError(null);
    try {
      await downloadFile("/api/admin/backup/snapshot", "arkon_snapshot.zip");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Snapshot failed");
    } finally {
      setBusy(false);
    }
  };

  const onRestore = async () => {
    if (!file || confirm !== "RESTORE") return;
    if (!window.confirm("This OVERWRITES the entire database and file storage. Continue?")) return;
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("confirm", confirm);
      const res = await apiUpload<{ minio_uploaded: number }>(
        "/api/admin/backup/snapshot/restore",
        fd,
        600_000,
      );
      setDone(`Snapshot restored. Files restored: ${res.minio_uploaded}. Reload the app.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Restore failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span className="material-symbols-outlined text-lg">backup</span>
          Full snapshot (advanced)
        </CardTitle>
        <CardDescription>
          A complete <code>pg_dump</code> + file-storage mirror for disaster recovery. Restoring a
          snapshot replaces <strong>everything</strong>.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {error && <p className="text-sm text-destructive">{error}</p>}
        {done && <p className="text-sm text-green-600 dark:text-green-400">{done}</p>}

        <div>
          <Button variant="outline" onClick={onDownload} disabled={busy}>
            {busy ? (
              <span className="material-symbols-outlined animate-spin">progress_activity</span>
            ) : (
              <span className="material-symbols-outlined">download</span>
            )}
            Download full snapshot
          </Button>
        </div>

        <div className="flex flex-col gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3">
          <span className="text-sm font-medium text-destructive">Restore snapshot (destructive)</span>
          <Input
            type="file"
            accept=".zip"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="confirm-restore">
              Type <code>RESTORE</code> to confirm
            </Label>
            <Input
              id="confirm-restore"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="RESTORE"
            />
          </div>
          <div>
            <Button
              variant="destructive"
              onClick={onRestore}
              disabled={busy || !file || confirm !== "RESTORE"}
            >
              <span className="material-symbols-outlined">restore</span>
              Restore snapshot
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
