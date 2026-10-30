"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Empty, ErrorNote, PageTitle, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { when } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

type Row = { id: string; status: string; intent: string; domains: string[]; created_at: string; outcome_headline?: string };
const STATUSES = ["", "VERIFIED", "PARTIALLY_VERIFIED", "NEEDS_APPROVAL", "UNCERTAIN", "FAILED", "CANCELLED"];
const DOMAINS = ["", "travel", "retail", "banking", "consumer_rights"];

export default function History() {
  const { lang } = useI18n();
  const [q, setQ] = useState(""); const [status, setStatus] = useState(""); const [domain, setDomain] = useState("");
  const [rows, setRows] = useState<Row[] | null>(null); const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const p = new URLSearchParams({ limit: "50" }); if (q) p.set("q", q); if (status) p.set("status", status); if (domain) p.set("domain", domain);
    const h = setTimeout(() => { api<{ items: Row[] }>(`/missions?${p}`).then((r) => setRows(r.items)).catch((e) => setError(e.message)); }, 200);
    return () => clearTimeout(h);
  }, [q, status, domain]);
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageTitle title="Mission history" />
      <ErrorNote error={error} />
      <div className="grid gap-3 sm:grid-cols-3">
        <div><label className="label" htmlFor="q">Search</label><input id="q" className="input" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        <div><label className="label" htmlFor="st">Status</label><select id="st" className="input" value={status} onChange={(e) => setStatus(e.target.value)}>{STATUSES.map((s) => <option key={s} value={s}>{s ? s.replaceAll("_", " ").toLowerCase() : "All"}</option>)}</select></div>
        <div><label className="label" htmlFor="dm">Domain</label><select id="dm" className="input" value={domain} onChange={(e) => setDomain(e.target.value)}>{DOMAINS.map((s) => <option key={s} value={s}>{s || "All"}</option>)}</select></div>
      </div>
      {rows === null ? <p className="text-muted" role="status">Loading…</p> : rows.length === 0 ? <Empty title="No missions match" /> : (
        <ul className="space-y-2">{rows.map((r) => (<li key={r.id}><Link className="card flex flex-col gap-2 p-4 hover:border-indigo sm:flex-row sm:items-center sm:justify-between" href={`/app/missions/${r.id}`}>
          <span className="min-w-0"><span className="block truncate font-semibold">{r.intent}</span><span className="text-xs text-muted">{when(r.created_at, lang)} · {r.domains.join(", ") || "unclassified"}</span></span><StatusBadge status={r.status} /></Link></li>))}</ul>)}
    </div>
  );
}
