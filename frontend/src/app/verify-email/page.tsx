"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ApiError, setToken } from "@/lib/api";

export default function VerifyEmailPage() {
  const router = useRouter();
  const [state, setState] = useState<"working" | "ok" | "error">("working");
  const [message, setMessage] = useState("Đang xác thực email…");

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get("token");
    if (!token) {
      setState("error");
      setMessage("Thiếu mã xác thực.");
      return;
    }
    api<{ access_token: string }>("/api/auth/verify-email", {
      method: "POST",
      body: { token },
    })
      .then((res) => {
        setToken(res.access_token);
        setState("ok");
        setMessage("Xác thực thành công! Đang chuyển hướng…");
        setTimeout(() => {
          window.location.href = "/chess";
        }, 1200);
      })
      .catch((err) => {
        setState("error");
        setMessage(err instanceof ApiError ? err.message : "Xác thực thất bại.");
      });
  }, [router]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="w-full max-w-md px-8 text-center">
        <h1 className="text-4xl tracking-tight text-foreground mb-6">Arkon</h1>
        <div className="bg-card rounded-xl border border-border shadow-sahara p-8">
          <span className={`material-symbols-outlined text-4xl ${state === "error" ? "text-destructive" : "text-primary"} ${state === "working" ? "animate-spin" : ""}`}>
            {state === "working" ? "progress_activity" : state === "ok" ? "check_circle" : "error"}
          </span>
          <p className="mt-3 text-sm text-muted-foreground">{message}</p>
          {state === "error" && (
            <Link href="/login" className="mt-4 inline-block text-sm text-primary hover:underline">
              Đến trang đăng nhập →
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
