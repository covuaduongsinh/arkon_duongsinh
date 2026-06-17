"use client";

/** Vertical evaluation bar. `scoreCp`/`mate` are from White's point of view. */

export function EvalBar({ scoreCp, mate }: { scoreCp: number | null; mate: number | null }) {
  // Map centipawns to a 0..1 white-fill fraction with a soft clamp.
  let whiteFrac = 0.5;
  let label = "0.0";
  if (mate !== null) {
    whiteFrac = mate > 0 ? 1 : 0;
    label = `M${Math.abs(mate)}`;
  } else if (scoreCp !== null) {
    const pawns = scoreCp / 100;
    whiteFrac = 1 / (1 + Math.pow(10, -pawns / 4));
    label = `${pawns >= 0 ? "+" : ""}${pawns.toFixed(1)}`;
  }

  return (
    <div className="flex h-full w-6 flex-col overflow-hidden rounded border border-black/10" title={label}>
      <div className="bg-[#262421]" style={{ height: `${(1 - whiteFrac) * 100}%` }} />
      <div className="flex-1 bg-[#f0e6d6]" />
      <span className="mx-auto -mt-4 text-[9px] font-semibold text-foreground/70">{label}</span>
    </div>
  );
}
