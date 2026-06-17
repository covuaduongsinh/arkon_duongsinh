"use client";

import Link from "next/link";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type RegisterResult = { status: "active" | "pending"; message: string };

export default function RegisterPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState<RegisterResult | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api<RegisterResult>("/api/auth/register", {
        method: "POST",
        body: { name, email, password },
      });
      setDone(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="w-full max-w-md px-8">
        <div className="text-center mb-10">
          <h1 className="text-5xl tracking-tight text-foreground mb-2">Arkon</h1>
          <p className="text-muted-foreground text-sm">Cờ vua Dương Sinh — Đăng ký học viên</p>
        </div>

        <div className="bg-card rounded-xl border border-border shadow-sahara p-8">
          {done ? (
            <div className="text-center">
              <span className="material-symbols-outlined text-4xl text-primary">
                {done.status === "active" ? "check_circle" : "mark_email_read"}
              </span>
              <h2 className="text-xl text-foreground mt-3 mb-2">Đăng ký thành công</h2>
              <p className="text-sm text-muted-foreground">{done.message}</p>
              <Link href="/login" className="mt-5 inline-block text-sm text-primary hover:underline">
                Đến trang đăng nhập →
              </Link>
            </div>
          ) : (
            <>
              <h2 className="text-2xl text-foreground mb-6">Tạo tài khoản</h2>
              <form onSubmit={handleSubmit} className="flex flex-col gap-5">
                <div className="flex flex-col gap-2">
                  <Label htmlFor="name" className="text-sm font-medium">Họ tên</Label>
                  <Input id="name" value={name} onChange={(e) => setName(e.target.value)} required autoFocus className="bg-background" />
                </div>
                <div className="flex flex-col gap-2">
                  <Label htmlFor="email" className="text-sm font-medium">Email</Label>
                  <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required className="bg-background" />
                </div>
                <div className="flex flex-col gap-2">
                  <Label htmlFor="password" className="text-sm font-medium">Mật khẩu (≥ 8 ký tự)</Label>
                  <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} className="bg-background" />
                </div>

                {error && (
                  <p className="text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-lg">{error}</p>
                )}

                <Button type="submit" disabled={loading} className="w-full bg-primary hover:bg-primary/90 text-primary-foreground mt-2">
                  {loading ? "Đang tạo..." : "Đăng ký"}
                </Button>
              </form>
            </>
          )}
        </div>

        <p className="text-center text-xs text-muted-foreground mt-6">
          Đã có tài khoản?{" "}
          <Link href="/login" className="text-primary hover:underline">Đăng nhập</Link>
        </p>
      </div>
    </div>
  );
}
