"use client";
import type { ReactNode } from "react";
import { useI18n } from "@/lib/i18n";
import { LANG_LABEL } from "@/lib/messages";
import type { Lang } from "@/lib/api";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export function Logo({ light = false }: { light?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2 font-extrabold tracking-tight">
      <svg width="30" height="30" viewBox="0 0 28 28" aria-hidden="true">
        <defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#7df0ff" /><stop offset="1" stopColor="#1596b3" /></linearGradient></defs>
        <rect width="28" height="28" rx="8" fill="url(#lg)" />
        <path d="M8 20V8h6.2c2.6 0 4.2 1.4 4.2 3.5 0 1.6-.9 2.7-2.4 3.2L19.5 20h-3l-2.8-4.8H10.6V20H8Zm2.6-7h3.4c1 0 1.7-.6 1.7-1.5S15 10 14 10h-3.4v3Z" fill="#03050A" />
      </svg>
      <span className={light ? "text-white" : "text-ink"}>REDEEM</span>
    </span>
  );
}

export function LangSwitcher({ className = "" }: { className?: string }) {
  const { lang, setLang } = useI18n();
  const { me } = useAuth();
  const change = async (l: Lang) => {
    setLang(l);
    if (me) { try { await api("/auth/language", { method: "PATCH", body: { language: l } }); } catch { /* local preference still applies */ } }
  };
  return (
    <label className={`inline-flex items-center gap-2 text-sm ${className}`}>
      <span className="sr-only">Language</span>
      <select aria-label="Language" value={lang} onChange={(e) => void change(e.target.value as Lang)}
        className="min-h-[44px] rounded-xl border border-line bg-surface px-3 text-sm font-semibold">
        {(Object.keys(LANG_LABEL) as Lang[]).map((l) => <option key={l} value={l}>{LANG_LABEL[l]}</option>)}
      </select>
    </label>
  );
}

const TONE: Record<string, string> = {
  VERIFIED: "bg-teal-soft text-teal", PARTIALLY_VERIFIED: "bg-amber-soft text-ink", NEEDS_APPROVAL: "bg-amber-soft text-ink",
  DISCOVERING: "bg-indigo-soft text-indigo", AUTHORIZED: "bg-indigo-soft text-indigo", EXECUTING: "bg-indigo-soft text-indigo",
  UNCERTAIN: "bg-amber-soft text-ink", FAILED: "bg-danger-soft text-danger", CANCELLED: "bg-soft text-muted",
};
export function StatusBadge({ status }: { status: string }) {
  const { t } = useI18n();
  const label = t(`status.${status}`);
  return <span className={`badge ${TONE[status] ?? "bg-soft text-muted"}`}>{label.startsWith("status.") ? status.replaceAll("_", " ").toLowerCase() : label}</span>;
}

export function Tag({ children, tone = "soft" }: { children: ReactNode; tone?: "soft" | "teal" | "amber" | "indigo" | "danger" }) {
  const c = { soft: "bg-soft text-muted", teal: "bg-teal-soft text-teal", amber: "bg-amber-soft text-ink", indigo: "bg-indigo-soft text-indigo", danger: "bg-danger-soft text-danger" }[tone];
  return <span className={`badge ${c}`}>{children}</span>;
}

export function PageTitle({ title, sub }: { title: string; sub?: string }) {
  return (<header className="mb-6"><h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">{title}</h1>{sub && <p className="mt-1 max-w-2xl text-muted">{sub}</p>}</header>);
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (<div className="rounded-2xl border border-dashed border-line p-8 text-center"><p className="font-semibold">{title}</p>{children && <p className="mt-1 text-sm text-muted">{children}</p>}</div>);
}

export function ErrorNote({ error }: { error: string | null }) {
  return error ? <p role="alert" className="rounded-xl bg-danger-soft px-4 py-3 text-sm font-medium text-danger">{error}</p> : null;
}
