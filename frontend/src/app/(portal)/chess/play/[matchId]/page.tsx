"use client";

import Link from "next/link";
import { Chess } from "chess.js";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { t } from "@/lib/i18n";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ChessBoard, type BoardMove } from "@/components/chess/ChessBoard";
import type { ChessMatch } from "@/types/chess";

type ChatMessage = { sender_id: string; sender_name: string; text: string; ts: number };

function turnColor(fen: string): "white" | "black" {
  try {
    return new Chess(fen).turn() === "w" ? "white" : "black";
  } catch {
    return "white";
  }
}

export default function ChessMatchPage() {
  const { matchId } = useParams<{ matchId: string }>();
  const { user } = useAuth();
  const [match, setMatch] = useState<ChessMatch | null>(null);
  const [loading, setLoading] = useState(true);
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const wsRef = useRef<WebSocket | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchMatch = useCallback(async () => {
    if (!matchId) return;
    try {
      const m = await api<ChessMatch>(`/api/chess/matches/${matchId}`);
      setMatch(m);
    } catch {
      /* keep previous */
    } finally {
      setLoading(false);
    }
  }, [matchId]);

  useEffect(() => {
    fetchMatch();
  }, [fetchMatch]);

  const myColor = match?.your_color ?? "white";
  const toMove = match ? turnColor(match.current_fen) : "white";
  const myTurn = !!match && match.status === "active" && myColor === toMove && !thinking;
  const waitingForOpponent =
    !!match && match.status === "active" && match.mode === "human_vs_human" && myColor !== toMove;

  // Realtime: subscribe to the match WebSocket for instant opponent updates.
  const status = match?.status;
  useEffect(() => {
    if (!matchId || status !== "active") return;
    const token = typeof window !== "undefined" ? localStorage.getItem("arkon_token") : null;
    if (!token) return;
    const base = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:5055").replace(/^http/, "ws");
    let ws: WebSocket;
    try {
      ws = new WebSocket(`${base}/api/chess/matches/${matchId}/ws?token=${encodeURIComponent(token)}`);
    } catch {
      return;
    }
    wsRef.current = ws;
    ws.onopen = () => setWsConnected(true);
    ws.onclose = () => setWsConnected(false);
    ws.onerror = () => setWsConnected(false);
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "state" && msg.match) {
          setMatch((prev) => (prev ? { ...prev, ...msg.match, your_color: prev.your_color } : prev));
        } else if (msg.type === "chat" && msg.message) {
          setMessages((prev) => [...prev, msg.message as ChatMessage]);
        }
      } catch {
        /* ignore */
      }
    };
    return () => {
      setWsConnected(false);
      wsRef.current = null;
      ws.close();
    };
  }, [matchId, status]);

  function sendChat(e: React.FormEvent) {
    e.preventDefault();
    const text = chatInput.trim();
    const ws = wsRef.current;
    if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: "chat", text }));
    setChatInput("");
  }

  // Poll as a fallback only while waiting for a human opponent AND WS is down.
  useEffect(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (waitingForOpponent && !wsConnected) {
      pollRef.current = setInterval(fetchMatch, 2000);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [waitingForOpponent, wsConnected, fetchMatch]);

  async function onMove(m: BoardMove) {
    if (!match || !myTurn) return;
    const uci = `${m.from}${m.to}${m.promotion ?? ""}`;
    setThinking(true);
    setError(null);
    try {
      const updated = await api<ChessMatch>(`/api/chess/matches/${match.id}/move`, {
        method: "POST",
        body: { uci },
      });
      setMatch(updated);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Move rejected");
      await fetchMatch();
    } finally {
      setThinking(false);
    }
  }

  async function resign() {
    if (!match || !confirm("Resign this match?")) return;
    try {
      const updated = await api<ChessMatch>(`/api/chess/matches/${match.id}/resign`, { method: "POST" });
      setMatch(updated);
    } catch {
      /* ignore */
    }
  }

  if (loading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (!match) return <p className="text-sm text-muted-foreground">Match not found.</p>;

  const lastUci = match.moves.length ? match.moves[match.moves.length - 1].uci : null;
  const lastMove = lastUci ? { from: lastUci.slice(0, 2), to: lastUci.slice(2, 4) } : null;

  const statusLabel =
    match.status === "finished"
      ? `Kết thúc — ${match.result}${
          match.winner_employee_id == null && match.result === "1/2-1/2" ? " (hoà)" : ""
        }`
      : myTurn
        ? t("Your move")
        : thinking
          ? t("Engine thinking…")
          : waitingForOpponent
            ? t("Waiting for opponent…")
            : t("Opponent to move");

  return (
    <>
      <PageHeader
        title={match.mode === "human_vs_engine" ? `Đấu Engine (cấp ${match.engine_level})` : "Đấu tập"}
        description={`Bạn cầm quân ${myColor === "white" ? "Trắng" : "Đen"}.`}
        action={
          <div className="flex items-center gap-2">
            <Badge variant={match.status === "active" ? "default" : "secondary"}>{statusLabel}</Badge>
            {match.status === "active" && (
              <Button variant="outline" size="sm" onClick={resign}>{t("Resign")}</Button>
            )}
          </div>
        }
      />

      <div className="flex flex-col gap-4 lg:flex-row">
        <ChessBoard
          fen={match.current_fen}
          orientation={myColor}
          interactive={myTurn}
          onMove={onMove}
          lastMove={lastMove}
        />
        <div className="w-full lg:w-64 shrink-0">
          {error && <p className="mb-2 text-sm text-destructive">{error}</p>}
          <div className="rounded-md border border-black/10 bg-card max-h-[420px] overflow-y-auto p-2 text-sm">
            {match.moves.length === 0 ? (
              <p className="p-2 text-muted-foreground">{t("No moves yet.")}</p>
            ) : (
              <div className="grid grid-cols-[auto_1fr_1fr] gap-x-2 gap-y-0.5">
                {Array.from({ length: Math.ceil(match.moves.length / 2) }).map((_, i) => (
                  <div key={i} className="contents">
                    <span className="tabular-nums py-0.5 text-muted-foreground/70">{i + 1}.</span>
                    <span className="px-1 py-0.5">{match.moves[i * 2]?.san}</span>
                    <span className="px-1 py-0.5">{match.moves[i * 2 + 1]?.san ?? ""}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
          {match.status === "finished" && match.game_id && (
            <Link href={`/chess/games/${match.game_id}`} className="mt-3 inline-block text-sm text-primary hover:underline">
              {t("View archived game →")}
            </Link>
          )}

          {match.mode === "human_vs_human" && (
            <div className="mt-3 rounded-md border border-black/10 bg-card">
              <div className="border-b border-black/10 px-2 py-1.5 text-xs font-medium text-muted-foreground">
                {t("Chat")}
              </div>
              <div className="flex max-h-48 flex-col gap-1 overflow-y-auto p-2 text-sm">
                {messages.length === 0 ? (
                  <p className="text-xs text-muted-foreground">{t("No messages yet.")}</p>
                ) : (
                  messages.map((m, i) => {
                    const mine = m.sender_id === user?.id;
                    return (
                      <div key={i} className={mine ? "text-right" : "text-left"}>
                        <span className="text-[10px] text-muted-foreground/70">{mine ? t("You") : m.sender_name}</span>
                        <p className={`inline-block rounded px-2 py-1 ${mine ? "bg-primary/10" : "bg-muted"}`}>{m.text}</p>
                      </div>
                    );
                  })
                )}
              </div>
              <form onSubmit={sendChat} className="flex gap-1 border-t border-black/10 p-2">
                <Input
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  placeholder={wsConnected ? t("Type a message…") : t("Connecting…")}
                  disabled={!wsConnected}
                  maxLength={500}
                  className="h-8"
                />
                <Button type="submit" size="sm" disabled={!wsConnected || !chatInput.trim()}>{t("Send")}</Button>
              </form>
            </div>
          )}
        </div>
      </div>

      <Link href="/chess/play" className="text-sm text-muted-foreground hover:text-foreground">{t("Back to Play")}</Link>
    </>
  );
}
