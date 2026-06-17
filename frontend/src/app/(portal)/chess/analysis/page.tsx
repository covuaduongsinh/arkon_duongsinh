"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { t } from "@/lib/i18n";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AnalysisPanel } from "@/components/chess/AnalysisPanel";

const DEFAULT_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

export default function ChessAnalysisPage() {
  const [fen, setFen] = useState(DEFAULT_FEN);
  const [fenInput, setFenInput] = useState("");

  // Seed from ?fen= without pulling in useSearchParams (avoids Suspense reqs).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const q = params.get("fen");
    if (q) {
      setFen(q);
      setFenInput(q);
    }
  }, []);

  return (
    <>
      <PageHeader
        title={t("Analysis")}
        description={t("Play moves on the board; Stockfish evaluates the position live.")}
      />

      <form
        className="flex max-w-2xl gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (fenInput.trim()) setFen(fenInput.trim());
        }}
      >
        <Input
          placeholder={t("Paste a FEN to load a position…")}
          value={fenInput}
          onChange={(e) => setFenInput(e.target.value)}
          className="font-mono text-xs"
        />
        <Button type="submit" variant="outline">{t("Load")}</Button>
      </form>

      <AnalysisPanel key={fen} initialFen={fen} />

      <Link href="/chess" className="text-sm text-muted-foreground hover:text-foreground">
        ← Back to Chess
      </Link>
    </>
  );
}
