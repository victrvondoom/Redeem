"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Empty, ErrorNote, PageTitle, StatusBadge, Tag } from "@/components/ui";
import { Tabs } from "@/components/viz";
import { api } from "@/lib/api";
import { inr, when } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

type Row = { id: string; status: string; intent: string; domains: string[]; created_at: string; outcome_headline?: string };
type CRow = { id: string; title: string; status: string; stage: string; domain_label: string; provider: string | null; claimed_paise: number | null; created_at: string };
const STATUSES = ["", "VERIFIED", "PARTIALLY_VERIFIED", "NEEDS_APPROVAL", "UNCERTAIN", "FAILED", "CANCELLED"];
const DOMAINS = ["", "travel", "retail", "banking", "consumer_rights", "crm", "telecom", "housing", "government", "healthcare", "insurance", "ecommerce"];

export default function History() {
  const { lang } = useI18n();
  const [tab, setTab] = useState("missions");
  const [q, setQ] = useState(""); const [status, setStatus] = useState(""); const [domain, setDomain] = useState(""); const [page, setPage] = useState(0);
  const [rows, setRows] = useState<Row[] | null>(null); const [total, setTotal] = useState(0); const [crows, setCrows] = useState<CRow[] | null>(null); const [ctotal, setCtotal] = useState(0); const [error, setError] = useState<string | null>(null);
  const LIMIT = 10;
  useEffect(() => {
    const p = new URLSearchParams({ limit: String(LIMIT), offset: String(page * LIMIT) }); if (q) p.set("q", q);
    const h = setTimeout(() => {
      if (tab === "missions") { if (status) p.set("status", status); if (domain) p.set("domain", domain); api<{ items: Row[]; total: number }>(`/missions?${p}`).then((r) => { setRows(r.items); setTotal(r.total); }).catch((e) => setError(e.message)); }
      else api<{ items: CRow[]; total: number }>(`/cases?${p}`).then((r) => { setCrows(r.items); setCtotal(r.total); }).catch((e) => setError(e.message));
    }, 200);
    return () => clearTimeout(h);
  }, [tab, q, status, domain, page]);
  const n = tab === "missions" ? total : ctotal;
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageTitle title="History" sub="Every mission and case, searchable and persistent. Open one to see its timeline, evidence and report." />
      <ErrorNote error={error} />
      <Tabs value={tab} onChange={(t) => { setTab(t); setPage(0); }} tabs={[{ id: "missions", label: "Missions", count: tab === "missions" ? total : undefined }, { id: "cases", label: "Cases", count: tab === "cases" ? ctotal : undefined }]} />
      <div className="grid gap-3 sm:grid-cols-3"><div><label className="label" htmlFor="q">Search</label><input id="q" className="input" value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} /></div>
        {tab === "missions" && (<><div><label className="label" htmlFor="st">Status</label><select id="st" className="input" value={status} onChange={(e) => { setStatus(e.target.value); setPage(0); }}>{STATUSES.map((s) => <option key={s} value={s}>{s ? s.replaceAll("_", " ").toLowerCase() : "All"}</option>)}</select></div>
          <div><label className="label" htmlFor="dm">Domain</label><select id="dm" className="input" value={domain} onChange={(e) => { setDomain(e.target.value); setPage(0); }}>{DOMAINS.map((s) => <option key={s} value={s}>{s || "All"}</option>)}</select></div></>)}</div>
      {tab === "missions" ? (rows === null ? <p className="text-muted" role="status">Loading…</p> : rows.length === 0 ? <Empty title="No missions match" /> : (
        <ul className="space-y-2">{rows.map((r) => (<li key={r.id}><Link className="card flex flex-col gap-2 p-4 hover:border-indigo sm:flex-row sm:items-center sm:justify-between" href={`/app/missions/${r.id}`}>
          <span className="min-w-0"><span className="block truncate font-semibold">{r.intent}</span><span className="text-xs text-muted">{when(r.created_at, lang)} · {r.domains.join(", ") || "unclassified"}</span></span><StatusBadge status={r.status} /></Link></li>))}</ul>))
        : (crows === null ? <p className="text-muted" role="status">Loading…</p> : crows.length === 0 ? <Empty title="No cases match" /> : (
          <ul className="space-y-2">{crows.map((r) => (<li key={r.id}><Link className="card flex flex-col gap-2 p-4 hover:border-indigo sm:flex-row sm:items-center sm:justify-between" href={`/app/cases/${r.id}`}>
            <span className="min-w-0"><span className="block truncate font-semibold">{r.title}</span><span className="text-xs text-muted">{when(r.created_at, lang)} · {r.provider ?? "—"}{r.claimed_paise ? ` · ${inr(r.claimed_paise)}` : ""}</span></span><span className="flex gap-2"><Tag>{r.domain_label}</Tag><Tag tone="indigo">{r.status.replaceAll("_", " ").toLowerCase()}</Tag></span></Link></li>))}</ul>))}
      <div className="flex items-center justify-between text-sm text-muted"><span>{n} total</span><div className="flex gap-2"><button className="btn-ghost" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button><button className="btn-ghost" disabled={(page + 1) * LIMIT >= n} onClick={() => setPage(page + 1)}>Next</button></div></div>
    </div>
  );
}
