"use client";

import React from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { WikiPageDetail, WikiScope } from "@/types/wiki";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  page: WikiPageDetail;
  scopes: WikiScope[];
  onMoved: () => void;
};

export function WikiMovePageDialog({ open, onOpenChange, page, scopes, onMoved }: Props) {
  const currentScopeKey = `${page.scope_type ?? "global"}:${page.scope_id ?? ""}`;

  const targetScopes = scopes.filter(
    (s) => `${s.scope_type}:${s.scope_id ?? ""}` !== currentScopeKey,
  );

  const [targetKey, setTargetKey] = React.useState<string>("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!open) return;
    setTargetKey(targetScopes[0] ? `${targetScopes[0].scope_type}:${targetScopes[0].scope_id ?? ""}` : "");
    setError(null);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const [targetScopeType, targetScopeIdRaw] = targetKey.split(":");
  const targetScopeId = targetScopeIdRaw || null;

  const showWarning =
    (page.scope_type === "global" || !page.scope_type) &&
    targetScopeType === "department";

  const submit = async () => {
    if (!targetKey) return;
    setBusy(true);
    setError(null);
    try {
      const srcQs =
        page.scope_type && page.scope_type !== "global"
          ? `?scope_type=${page.scope_type}&scope_id=${page.scope_id ?? ""}`
          : "";
      await api(`/api/wiki/pages/${encodeURIComponent(page.slug)}/move${srcQs}`, {
        method: "POST",
        body: {
          target_scope_type: targetScopeType,
          target_scope_id: targetScopeId ?? undefined,
        },
      });
      onOpenChange(false);
      onMoved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Move failed");
    } finally {
      setBusy(false);
    }
  };

  const currentScopeName =
    scopes.find((s) => `${s.scope_type}:${s.scope_id ?? ""}` === currentScopeKey)?.name ??
    (page.scope_type === "global" ? "Global" : page.scope_type);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Chuyển trang sang scope khác</DialogTitle>
          <DialogDescription>
            Trang hiện tại đang ở scope:{" "}
            <span className="font-medium text-foreground">{currentScopeName}</span>
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-2">
          <div className="grid gap-1.5">
            <label
              htmlFor="move-target-scope"
              className="text-sm font-medium leading-none"
            >
              Chuyển đến
            </label>
            {targetScopes.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Không có scope nào khác để chuyển đến.
              </p>
            ) : (
              <select
                id="move-target-scope"
                value={targetKey}
                onChange={(e) => setTargetKey(e.target.value)}
                className="h-9 rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                {targetScopes.map((s) => (
                  <option
                    key={`${s.scope_type}:${s.scope_id ?? ""}`}
                    value={`${s.scope_type}:${s.scope_id ?? ""}`}
                  >
                    {s.name} {s.scope_type !== "global" ? `(${s.scope_type})` : ""}
                  </option>
                ))}
              </select>
            )}
          </div>

          {showWarning && (
            <div className="flex gap-2.5 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-800/50 dark:bg-amber-900/20 dark:text-amber-300">
              <span className="material-symbols-outlined text-base shrink-0 mt-0.5">warning</span>
              <div className="space-y-1">
                <p className="font-medium">Chuyển từ Global sẽ giới hạn visibility</p>
                <p className="text-amber-700 dark:text-amber-400">
                  Trang này hiện hiển thị với toàn bộ tổ chức. Sau khi chuyển, chỉ thành viên
                  của department đó mới xem được. Các wikilink từ Global wiki trỏ đến trang
                  này có thể bị unresolved.
                </p>
              </div>
            </div>
          )}

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Hủy
          </Button>
          <Button
            onClick={submit}
            disabled={busy || !targetKey || targetScopes.length === 0}
            className="gap-1.5"
          >
            {busy ? (
              <span className="material-symbols-outlined text-sm animate-spin">
                progress_activity
              </span>
            ) : (
              <span className="material-symbols-outlined text-sm">drive_file_move</span>
            )}
            Chuyển trang
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
