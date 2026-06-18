"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { ChessBoard } from "@/components/chess/ChessBoard";
import { PgnViewer } from "@/components/chess/PgnViewer";

type Lesson = { id: string; class_id: string; title: string; content_md: string; wiki_slug?: string | null };

export default function LessonPage() {
  const { id } = useParams<{ id: string }>();
  const { hasPermission } = useAuth();
  const canCoach = hasPermission("chess:coach");
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [loading, setLoading] = useState(true);
  const [publishing, setPublishing] = useState(false);
  const [publishMsg, setPublishMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api<Lesson>(`/api/chess/lessons/${id}`)
      .then(setLesson)
      .catch(() => setLesson(null))
      .finally(() => setLoading(false));
  }, [id]);

  async function publishWiki() {
    setPublishing(true);
    setPublishMsg(null);
    try {
      const r = await api<{ draft_id: string; slug: string; status: string }>(
        `/api/chess/lessons/${id}/publish-wiki`,
        { method: "POST" },
      );
      setPublishMsg(`Đã gửi vào hàng đợi Duyệt bài (slug: ${r.slug}). Khi được duyệt, trang wiki sẽ xuất hiện.`);
      setLesson((prev) => (prev ? { ...prev, wiki_slug: r.slug } : prev));
    } catch (e) {
      setPublishMsg(e instanceof ApiError ? e.message : "Không thể xuất bản lên wiki");
    } finally {
      setPublishing(false);
    }
  }

  if (loading) return <p className="text-sm text-muted-foreground">Đang tải…</p>;
  if (!lesson) return <p className="text-sm text-muted-foreground">Không tìm thấy bài giảng.</p>;

  return (
    <>
      <PageHeader
        title={lesson.title}
        action={
          <div className="flex items-center gap-2">
            {lesson.wiki_slug && (
              <Link href={`/wiki/${lesson.wiki_slug}`} className="text-sm text-primary hover:underline inline-flex items-center gap-1">
                <span className="material-symbols-outlined text-sm">menu_book</span>
                Trang wiki
              </Link>
            )}
            {canCoach && (
              <Button variant="outline" size="sm" onClick={publishWiki} disabled={publishing} className="gap-1.5">
                <span className="material-symbols-outlined text-sm">upload</span>
                {publishing ? "Đang gửi…" : "Xuất bản lên Wiki"}
              </Button>
            )}
          </div>
        }
      />
      {publishMsg && (
        <p className="mb-4 rounded-md border border-black/10 bg-muted/40 px-3 py-2 text-sm text-muted-foreground">{publishMsg}</p>
      )}
      <div className="prose-sm max-w-3xl">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            // Render ```pgn / ```fen fenced blocks as interactive boards.
            pre: ({ children }) => {
              const child = Array.isArray(children) ? children[0] : children;
              const cls = (child as { props?: { className?: string } })?.props?.className ?? "";
              const text = String((child as { props?: { children?: string } })?.props?.children ?? "").trim();
              if (cls.includes("language-pgn") && text) return <div className="my-4"><PgnViewer pgn={text} /></div>;
              if (cls.includes("language-fen") && text) return <div className="my-4"><ChessBoard fen={text} className="max-w-[360px]" /></div>;
              return <pre className="overflow-x-auto rounded-md border border-black/10 bg-muted/40 p-3 text-xs">{children}</pre>;
            },
          }}
        >
          {lesson.content_md || "_(Chưa có nội dung)_"}
        </ReactMarkdown>
      </div>
      <Link href={`/chess/classes/${lesson.class_id}`} className="text-sm text-muted-foreground hover:text-foreground">← Về lớp</Link>
    </>
  );
}
