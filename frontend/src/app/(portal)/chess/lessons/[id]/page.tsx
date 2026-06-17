"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/shared/page-header";
import { ChessBoard } from "@/components/chess/ChessBoard";
import { PgnViewer } from "@/components/chess/PgnViewer";

type Lesson = { id: string; class_id: string; title: string; content_md: string };

export default function LessonPage() {
  const { id } = useParams<{ id: string }>();
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    api<Lesson>(`/api/chess/lessons/${id}`)
      .then(setLesson)
      .catch(() => setLesson(null))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <p className="text-sm text-muted-foreground">Đang tải…</p>;
  if (!lesson) return <p className="text-sm text-muted-foreground">Không tìm thấy bài giảng.</p>;

  return (
    <>
      <PageHeader title={lesson.title} />
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
