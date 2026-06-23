"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { EmptyState } from "@/components/shared/empty-state";
import { WikiStatusBadge } from "@/components/wiki/wiki-status-badge";

type WikiPageSummary = {
  slug: string;
  title: string;
  status: string;
  created_at: string;
};

export function RecentWikiPagesCard() {
  const [pages, setPages] = useState<WikiPageSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const data = await api<WikiPageSummary[]>(
          "/api/wiki/pages?sort=created&limit=5"
        );
        setPages(data || []);
      } catch {
        setPages([]);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return (
    <div className="bg-card rounded-xl p-6 border border-border shadow-sahara">
      <h3 className="text-xl tracking-tight text-foreground border-b border-border pb-3 mb-4">
        Trang Wiki tạo gần đây
      </h3>

      {loading ? (
        <div className="flex items-center justify-center py-8">
          <span className="material-symbols-outlined text-2xl text-muted-foreground animate-spin">
            progress_activity
          </span>
        </div>
      ) : pages.length === 0 ? (
        <EmptyState
          icon="auto_stories"
          title="Chưa có trang wiki nào"
          description="Các trang wiki mới tạo sẽ xuất hiện ở đây."
        />
      ) : (
        <div className="flex flex-col gap-3">
          {pages.map((page) => (
            <Link
              key={page.slug}
              href={`/wiki/${page.slug}`}
              className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-secondary/50 transition-colors"
            >
              <div className="flex items-center gap-3 min-w-0">
                <span className="material-symbols-outlined text-muted-foreground text-base">
                  auto_stories
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">
                    {page.title}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {page.created_at
                      ? new Date(page.created_at).toLocaleDateString()
                      : ""}
                  </p>
                </div>
              </div>
              <div className="shrink-0">
                <WikiStatusBadge status={page.status} />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
