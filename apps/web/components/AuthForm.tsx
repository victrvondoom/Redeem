"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { ErrorNote, LangSwitcher, Logo } from "./ui";

function Form({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const next = useSearchParams().get("next");
  const { refresh } = useAuth();
  const { lang } = useI18n();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const safeNext = next && next.startsWith("/app") ? next : "/app";

  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true); setError(null);
    try {
      if (mode === "register") await api("/auth/register", { body: { email: f.get("email"), password: f.get("password"), name: f.get("name"), language: lang } });
      else await api("/auth/login", { body: { email: f.get("email"), password: f.get("password") } });
      await refresh();
      router.push(safeNext);
    } catch (err) { setError(err instanceof ApiError ? err.message : "Something went wrong."); setBusy(false); }
  };

  return (
    <main id="main" className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4 py-10">
      <div className="mb-6 flex items-center justify-between"><Link href="/"><Logo /></Link><LangSwitcher /></div>
      <form onSubmit={submit} className="card space-y-4" aria-labelledby="auth-h">
        <h1 id="auth-h" className="text-2xl font-extrabold">{mode === "register" ? "Create your workspace" : "Welcome back"}</h1>
        {mode === "register" && (<div><label className="label" htmlFor="name">Name</label><input id="name" name="name" className="input" required maxLength={120} autoComplete="name" /></div>)}
        <div><label className="label" htmlFor="email">Email</label><input id="email" name="email" type="email" className="input" required autoComplete="email" /></div>
        <div><label className="label" htmlFor="password">Password</label>
          <input id="password" name="password" type="password" className="input" required minLength={mode === "register" ? 10 : 1} autoComplete={mode === "register" ? "new-password" : "current-password"} />
          {mode === "register" && <p className="mt-1 text-xs text-muted">At least 10 characters.</p>}</div>
        <ErrorNote error={error} />
        <button className="btn-primary w-full" disabled={busy}>{mode === "register" ? "Create account" : "Sign in"}</button>
        <p className="text-center text-sm text-muted">{mode === "register" ? <>Have an account? <Link className="font-semibold text-indigo" href={`/login${next ? `?next=${encodeURIComponent(next)}` : ""}`}>Sign in</Link></> : <>New here? <Link className="font-semibold text-indigo" href="/register">Create an account</Link></>}</p>
      </form>
    </main>
  );
}
export const AuthForm = ({ mode }: { mode: "login" | "register" }) => <Suspense><Form mode={mode} /></Suspense>;
