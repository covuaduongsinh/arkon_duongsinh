"use client";

/** Eval graph — a sparkline of white-POV centipawns across the game. */

export function EvalGraph({ evals }: { evals: number[] }) {
  if (!evals.length) return null;
  const W = 480;
  const H = 96;
  const mid = H / 2;
  const CAP = 1000; // clamp eval to ±10 pawns for display

  const pts = evals.map((cp, i) => {
    const x = (i / Math.max(1, evals.length - 1)) * W;
    const clamped = Math.max(-CAP, Math.min(CAP, cp));
    const y = mid - (clamped / CAP) * (mid - 4);
    return [x, y] as const;
  });

  const line = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  // Area path (fill under the line down to the midline).
  const area = `0,${mid} ${line} ${W},${mid}`;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full rounded-md border border-black/10 bg-card" preserveAspectRatio="none" style={{ height: H }}>
      <line x1="0" y1={mid} x2={W} y2={mid} stroke="rgba(0,0,0,0.15)" strokeWidth="1" />
      <polygon points={area} fill="rgba(194,101,42,0.12)" />
      <polyline points={line} fill="none" stroke="#c2652a" strokeWidth="1.5" />
    </svg>
  );
}
