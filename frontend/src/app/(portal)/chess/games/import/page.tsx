"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { apiUpload, ApiError } from "@/lib/api";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

type ImportResult = { imported: number };

export default function ChessImportPage() {
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [pgn, setPgn] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setError(null);
    const file = fileRef.current?.files?.[0];
    if (!file && !pgn.trim()) {
      setError("Provide a PGN file or paste PGN text.");
      return;
    }
    setBusy(true);
    try {
      const form = new FormData();
      if (file) form.append("file", file);
      else form.append("pgn", pgn);
      form.append("scope_type", "global");
      const res = await apiUpload<ImportResult>("/api/chess/games/import", form);
      router.push(`/chess/games`);
      void res;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Import failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Import PGN" description="Add one or many games from a .pgn file or pasted text." />

      <div className="max-w-2xl space-y-4">
        <div>
          <label className="mb-1 block text-sm font-medium">PGN file</label>
          <input
            ref={fileRef}
            type="file"
            accept=".pgn,text/plain"
            onChange={(e) => setFileName(e.target.files?.[0]?.name ?? null)}
            className="block w-full text-sm file:mr-3 file:rounded-md file:border file:border-black/10 file:bg-muted file:px-3 file:py-1.5 file:text-sm"
          />
          {fileName && <p className="mt-1 text-xs text-muted-foreground">{fileName}</p>}
        </div>

        <div className="flex items-center gap-3 text-xs uppercase tracking-wide text-muted-foreground/60">
          <div className="h-px flex-1 bg-black/10" /> or paste <div className="h-px flex-1 bg-black/10" />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium">PGN text</label>
          <Textarea
            value={pgn}
            onChange={(e) => setPgn(e.target.value)}
            rows={10}
            placeholder={'[Event "..."]\n[White "..."]\n[Black "..."]\n\n1. e4 e5 2. Nf3 ...'}
            className="font-mono text-xs"
          />
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="flex gap-2">
          <Button onClick={submit} disabled={busy}>
            {busy ? "Importing…" : "Import"}
          </Button>
          <Link href="/chess/games">
            <Button variant="outline">Cancel</Button>
          </Link>
        </div>
      </div>
    </>
  );
}
