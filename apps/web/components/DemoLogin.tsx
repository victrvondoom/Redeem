"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/** One-click demo login: opens a fresh, isolated workspace with labelled practice data. Anyone can use it; the server turns it off in production. */
export function DemoLogin({ className = "btn", label = "Demo login" }: { className?: string; label?: string }) {
  const router = useRouter();
  const { refresh } = useAuth();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const go = async () => {
    setBusy(true); setErr(null);
    try { await api("/auth/demo", { method: "POST" }); await refresh(); router.push("/app"); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Could not start the demo."); setBusy(false); }
  };
  return (<>
    <button type="button" className={className} onClick={() => void go()} disabled={busy} data-testid="demo-signin">{busy ? "Opening demo…" : label}</button>
    {err && <span role="alert" className="text-sm text-danger">{err}</span>}
  </>);
}
