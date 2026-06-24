"use client";

import React from "react";
import { createPortal } from "react-dom";

/** One row in the `[[` picker — a wiki page or a chess entity. The parent
 *  (markdown-editor) builds and orders these; this component only renders +
 *  handles keyboard nav. `insert` is the text written before the closing `]]`. */
export type LinkSuggestion = {
  kind: "wiki" | "chess";
  insert: string;
  title: string;
  subtitle?: string | null;
  icon: string;
  iconColor?: string;
  key: string;
};

type Props = {
  items: LinkSuggestion[];
  /** Viewport-relative caret position; popup anchors just below this line. */
  caret: { top: number; left: number; lineHeight: number };
  onPick: (item: LinkSuggestion) => void;
  onClose: () => void;
};

const POPUP_WIDTH = 360;
const POPUP_MAX_HEIGHT = 300;

export function WikilinkAutocomplete({ items, caret, onPick, onClose }: Props) {
  const [active, setActive] = React.useState(0);

  // Reset selection whenever the suggestion set changes.
  React.useEffect(() => {
    setActive(0);
  }, [items]);

  // Keyboard handler attached to window — the textarea is focused, not the popup.
  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (items.length === 0) {
        if (e.key === "Escape") onClose();
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActive((i) => (i + 1) % items.length);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActive((i) => (i - 1 + items.length) % items.length);
      } else if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        const pick = items[active];
        if (pick) onPick(pick);
      } else if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    // capture: true so we run before the textarea's own key handlers.
    window.addEventListener("keydown", handler, true);
    return () => window.removeEventListener("keydown", handler, true);
  }, [items, active, onPick, onClose]);

  if (typeof window === "undefined") return null;

  // Anchor the popup just under the caret line. Flip above when it would
  // overflow the viewport bottom.
  const top = caret.top + caret.lineHeight + 4;
  const left = caret.left;
  const flipUp = top + POPUP_MAX_HEIGHT > window.innerHeight - 16;
  const finalTop = flipUp ? caret.top - POPUP_MAX_HEIGHT - 4 : top;
  const finalLeft = Math.min(left, window.innerWidth - POPUP_WIDTH - 16);

  return createPortal(
    <div
      style={{
        position: "fixed",
        top: finalTop,
        left: finalLeft,
        width: POPUP_WIDTH,
        maxHeight: POPUP_MAX_HEIGHT,
        zIndex: 100,
      }}
      className="rounded-lg border border-border bg-popover text-popover-foreground shadow-lg overflow-hidden flex flex-col"
      onMouseDown={(e) => e.preventDefault()} // keep textarea focused
    >
      <div className="px-3 py-1.5 border-b border-border bg-muted/40 flex items-center justify-between text-[10px] uppercase tracking-wide text-muted-foreground">
        <span>Chèn liên kết</span>
        <span className="font-mono">↑↓ Enter</span>
      </div>
      {items.length === 0 ? (
        <div className="px-3 py-4 text-xs text-muted-foreground italic">Không có gợi ý.</div>
      ) : (
        <ul className="overflow-y-auto py-1" style={{ maxHeight: POPUP_MAX_HEIGHT - 32 }}>
          {items.map((it, i) => {
            const isActive = i === active;
            return (
              <li key={it.key}>
                <button
                  type="button"
                  onMouseEnter={() => setActive(i)}
                  onClick={() => onPick(it)}
                  className={`w-full flex items-start gap-2 px-3 py-2 text-left transition-colors ${
                    isActive ? "bg-accent" : "hover:bg-accent/50"
                  }`}
                >
                  <span
                    className="material-symbols-outlined shrink-0 mt-0.5"
                    style={{ fontSize: 16, color: it.iconColor }}
                  >
                    {it.icon}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm truncate">{it.title}</p>
                    <p className="text-[11px] text-muted-foreground font-mono truncate">
                      {it.subtitle ?? it.insert}
                    </p>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>,
    document.body,
  );
}
