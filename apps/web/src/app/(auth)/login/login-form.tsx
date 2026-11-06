"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Loader2 } from "lucide-react";

export function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data?.error?.message ?? "Sign-in failed");
        setPending(false);
        return;
      }
      router.replace("/");
      router.refresh();
    } catch {
      setError("Network error — is the API running?");
      setPending(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="email" className="mono-label text-ink">
          operator email
        </label>
        <input
          id="email"
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="admin@factory.app"
          className="h-9 border border-border bg-white px-3 text-[13.5px] outline-none transition-colors hover:border-ink focus:border-ink focus:ring-1 focus:ring-ink"
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="password" className="mono-label text-ink">
          password
        </label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••••••"
          className="h-9 border border-border bg-white px-3 text-[13.5px] outline-none transition-colors hover:border-ink focus:border-ink focus:ring-1 focus:ring-ink"
        />
      </div>

      {error && (
        <p role="alert" className="border-l-2 border-danger bg-[#FBEBEA] px-2 py-1.5 text-[12.5px] text-[#9B2C28]">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={pending}
        className="mt-1 flex h-9 items-center justify-center gap-2 border border-ink bg-ink text-[13px] font-medium text-white transition-colors hover:bg-white hover:text-ink disabled:opacity-50"
      >
        {pending ? <Loader2 className="size-3.5 animate-spin" /> : null}
        {pending ? "Signing in" : "Enter studio"}
        {!pending && <ArrowRight className="size-3.5" />}
      </button>
      <p className="border-t border-border pt-3 font-mono text-[10px] uppercase leading-relaxed tracking-[0.08em] text-subtle">
        Credentials from BOOTSTRAP_ADMIN_EMAIL · sessions are httpOnly cookies
      </p>
    </form>
  );
}
