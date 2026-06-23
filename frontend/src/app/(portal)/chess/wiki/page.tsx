"use client";

import React from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { t } from "@/lib/i18n";
import { WikiPageSummary, WikiScope } from "@/types/wiki";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/shared/empty-state";
import { ScopeBadge } from "@/components/shared/scope-badge";
import { WikiCreatePageDialog } from "@/components/wiki/wiki-create-page-dialog";
import { useAuth } from "@/lib/auth";

/* The chess knowledge-type family (seeded in migration 042). Order here drives
 * the section order on the page. The flat "chess" type and anything unmatched
 * fall into the "Khác" bucket. */
const CHESS_SECTIONS: { slug: string; label: string; icon: string }[] = [
  { slug: "chess-opening", label: "Khai cuộc", icon: "rocket_launch" },
  { slug: "chess-tactics", label: "Chiến thuật", icon: "swords" },
  { slug: "chess-endgame", label: "Tàn cuộc", icon: "flag" },
  { slug: "chess-strategy", label: "Chiến lược", icon: "strategy" },
  { slug: "chess-game", label: "Ván mẫu", icon: "menu_book" },
];

// Knowledge types offered when a teacher creates a chess wiki page.
const CHESS_KT_OPTIONS = [
  { slug: "chess-opening", label: "Khai cuộc" },
  { slug: "chess-tactics", label: "Chiến thuật" },
  { slug: "chess-endgame", label: "Tàn cuộc" },
  { slug: "chess-strategy", label: "Chiến lược" },
  { slug: "chess-game", label: "Ván mẫu" },
  { slug: "chess", label: "Khác (chung)" },
];

const OTHER_SECTION = { slug: "__other__", label: "Khác", icon: "category" };

function pageHref(page: WikiPageSummary): string {
  return page.scope_type && page.scope_type !== "global" && page.scope_id
    ? `/wiki/${page.slug}?scopeType=${page.scope_type}&scopeId=${page.scope_id}`
    : `/wiki/${page.slug}`;
}

export default function ChessWikiPage() {
  const { user, hasPermission } = useAuth();

  const [pages, setPages] = React.useState<WikiPageSummary[]>([]);
  const [scopes, setScopes] = React.useState<WikiScope[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [query, setQuery] = React.useState("");
  const [createOpen, setCreateOpen] = React.useState(false);

  React.useEffect(() => {
    setLoading(true);
    Promise.all([
      api<WikiPageSummary[]>("/api/wiki/pages?knowledge_family=chess&limit=500"),
      api<WikiScope[]>("/api/wiki/my-scopes").catch(() => [] as WikiScope[]),
    ])
      .then(([rows, scs]) => {
        setPages(Array.isArray(rows) ? rows : []);
        setScopes(Array.isArray(scs) ? scs : []);
      })
      .catch(() => {
        setPages([]);
        setScopes([]);
      })
      .finally(() => setLoading(false));
  }, []);

  // Global is the default create scope. Teachers (wiki:write:own_dept) propose;
  // editors/admins (wiki:write:all) create directly — both gated server-side.
  const isAdmin = user?.role === "admin";
  const createMode: "direct" | "propose" | null = React.useMemo(() => {
    if (!user) return null;
    if (isAdmin || hasPermission("wiki:write:all")) return "direct";
    if (hasPermission("wiki:write:own_dept")) return "propose";
    return null;
  }, [user, isAdmin, hasPermission]);

  const getCreateModeForScope = React.useCallback(
    (scope: { scope_type: string; scope_id: string | null }): "direct" | "propose" | null => {
      if (!user) return null;
      if (scope.scope_type === "department" && scope.scope_id) {
        if (isAdmin || hasPermission("wiki:write:all")) return "direct";
        if (hasPermission("wiki:write:own_dept") && user.department_ids.includes(scope.scope_id)) {
          return "propose";
        }
        return null;
      }
      if (isAdmin || hasPermission("wiki:write:all")) return "direct";
      if (hasPermission("wiki:write:own_dept")) return "propose";
      return null;
    },
    [user, isAdmin, hasPermission],
  );

  // Client-side, chess-scoped filter over the loaded set.
  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return pages;
    return pages.filter(
      (p) =>
        p.title.toLowerCase().includes(q) ||
        p.summary.toLowerCase().includes(q) ||
        p.slug.toLowerCase().includes(q),
    );
  }, [pages, query]);

  // Bucket pages by their first matching chess sub-topic; the rest go to "Khác".
  const grouped = React.useMemo(() => {
    const buckets: Record<string, WikiPageSummary[]> = {};
    for (const s of CHESS_SECTIONS) buckets[s.slug] = [];
    buckets[OTHER_SECTION.slug] = [];
    for (const p of filtered) {
      const match = CHESS_SECTIONS.find((s) => p.knowledge_type_slugs.includes(s.slug));
      buckets[match ? match.slug : OTHER_SECTION.slug].push(p);
    }
    return buckets;
  }, [filtered]);

  const allSections = [...CHESS_SECTIONS, OTHER_SECTION];

  return (
    <>
      <PageHeader
        title={t("Chess Wiki")}
        description={t(
          "Specialized chess knowledge for teachers — openings, tactics, endgames, strategy and model games.",
        )}
        action={
          createMode && (
            <Button
              onClick={() => setCreateOpen(true)}
              className="gap-2 bg-primary text-primary-foreground hover:bg-primary/90"
            >
              <span className="material-symbols-outlined text-base">add</span>
              {createMode === "direct" ? t("New page") : t("Propose page")}
            </Button>
          )
        }
      />

      {/* Scoped search */}
      <div className="relative mb-6 max-w-md">
        <span className="material-symbols-outlined text-sm text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2">
          search
        </span>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("Search the chess wiki…")}
          className="h-9 w-full pl-9 pr-3 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50 placeholder:text-muted-foreground/60"
        />
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <span className="material-symbols-outlined text-3xl text-muted-foreground animate-spin">
            progress_activity
          </span>
        </div>
      ) : pages.length === 0 ? (
        <EmptyState
          icon="menu_book"
          title={t("No chess wiki pages yet")}
          description={t(
            "Create a page or publish a lesson to the wiki to start building chess knowledge.",
          )}
        />
      ) : (
        <div className="flex flex-col gap-8">
          {allSections.map((section) => {
            const items = grouped[section.slug] ?? [];
            if (items.length === 0) return null;
            return (
              <section key={section.slug}>
                <div className="flex items-center gap-2 mb-3">
                  <span className="material-symbols-outlined text-lg text-primary">
                    {section.icon}
                  </span>
                  <h2 className="font-heading text-lg">{t(section.label)}</h2>
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {items.length}
                  </span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                  {items.map((page) => (
                    <Link
                      key={`${page.slug}-${page.scope_type ?? "global"}-${page.scope_id ?? "none"}`}
                      href={pageHref(page)}
                      className="group block bg-card border border-border rounded-xl p-4 hover:border-primary/40 hover:shadow-sahara transition-all"
                    >
                      <div className="flex items-start justify-between gap-2 mb-2">
                        {page.scope_type && page.scope_type !== "global" ? (
                          <ScopeBadge scopeType={page.scope_type} scopeId={page.scope_id} />
                        ) : (
                          <span />
                        )}
                        <span className="text-xs text-muted-foreground shrink-0">v{page.version}</span>
                      </div>
                      <h3 className="font-heading text-base font-normal text-foreground group-hover:text-primary transition-colors mb-1">
                        {page.title}
                      </h3>
                      {page.summary && (
                        <p className="text-xs text-muted-foreground line-clamp-2">{page.summary}</p>
                      )}
                    </Link>
                  ))}
                </div>
              </section>
            );
          })}
          {filtered.length === 0 && (
            <p className="text-sm text-muted-foreground">{t("No pages match your search.")}</p>
          )}
        </div>
      )}

      {createMode && (
        <WikiCreatePageDialog
          open={createOpen}
          onOpenChange={setCreateOpen}
          mode={createMode}
          defaultScope={{ scope_type: "global", scope_id: null, name: "Global" }}
          scopes={scopes}
          getCreateModeForScope={getCreateModeForScope}
          knowledgeTypeOptions={CHESS_KT_OPTIONS}
          defaultKnowledgeTypeSlug="chess-opening"
        />
      )}
    </>
  );
}
