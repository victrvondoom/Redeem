"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Empty, ErrorNote, PageTitle, Tag } from "@/components/ui";
import { Meter } from "@/components/viz";
import { api, ApiError } from "@/lib/api";
import { inr, when } from "@/lib/format";

type Row = { id: string; title: string; domain: string; domain_label: string; status: string; stage: string; provider: string | null; claimed_paise: number | null; followup_date: string | null; overdue: boolean; confidence: number | null; missing: number; updated_at: string };
type Rad = { institution: string; cases: number; domains: string[]; claimed_paise: number; resolved: number; unresolved: number; open: number; issues: Record<string, number> };
type Dom = { id: string; label: string; counterparty: string; regulator: string; my_cases: number };
const EXAMPLES: Record<string, string> = {
  travel: "My IndiGo flight 6E-2134 on 15 January 2026 was cancelled and they refused a refund of Rs 8,500. PNR: ABC123",
  banking: "Rs 12,500 was debited on 2026-01-15 from my HDFC Bank account without my consent. UTR 123456789012. The bank rejected my dispute.",
  insurance: "Star Health rejected my claim of Rs 3,50,000 for surgery at Apollo Hospitals, citing a pre-existing condition. Policy number STAR/123456",
  telecom: "My Jio postpaid bill for December shows Rs 1,299 of extra charges I never used. Complaint no: CMP-8812 got no resolution.",
  ecommerce: "Flipkart refused to take back my damaged phone. Order ID OD123456789012 for Rs 18,999 delivered on 3 March 2026, the return was refused.",
  housing: "My landlord is refusing to return my security deposit of Rs 50,000 after I vacated on 1 February 2026.",
  government: "My passport application is pending for 4 months with no update from the department. Application number: PSP12345",
  healthcare: "Apollo Hospital charged me Rs 25,000 twice on the final bill dated 10 February 2026, an overcharged invoice.",
};
const STATUS_TONE: Record<string, "teal" | "amber" | "indigo" | "danger" | "soft"> = { AWAITING_INFO: "indigo", AWAITING_APPROVAL: "amber", APPROVED: "indigo", SUBMITTED: "indigo", TRACKING: "indigo", RESOLVED: "teal", UNRESOLVED: "danger", CLOSED: "soft", OPEN: "soft" };

export default function Cases() {
  const router = useRouter();
  const [rows, setRows] = useState<Row[] | null>(null);
  const [total, setTotal] = useState(0);
  const [doms, setDoms] = useState<Dom[]>([]);
  const [q, setQ] = useState(""); const [domain, setDomain] = useState(""); const [status, setStatus] = useState(""); const [sort, setSort] = useState("updated"); const [page, setPage] = useState(0);
  const [radar, setRadar] = useState<{ items: Rad[]; scope: string } | null>(null);
  const [text, setText] = useState(""); const [newDomain, setNewDomain] = useState(""); const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null);
  const LIMIT = 8;

  const load = useCallback(async () => {
    const p = new URLSearchParams({ limit: String(LIMIT), offset: String(page * LIMIT), sort, order: sort === "title" ? "asc" : "desc" });
    if (q) p.set("q", q); if (domain) p.set("domain", domain); if (status) p.set("status", status);
    try { const r = await api<{ items: Row[]; total: number }>(`/cases?${p}`); setRows(r.items); setTotal(r.total); } catch (e) { setError(e instanceof Error ? e.message : "Failed to load"); }
  }, [q, domain, status, sort, page]);
  useEffect(() => { const h = setTimeout(() => void load(), 200); return () => clearTimeout(h); }, [load]);
  useEffect(() => { api<{ items: Rad[]; scope: string }>("/intelligence/radar").then(setRadar).catch(() => undefined); }, [rows]);
  useEffect(() => { api<{ items: Dom[] }>("/reclaim/domains").then((r) => setDoms(r.items)).catch(() => undefined); }, []);

  const create = async () => {
    setBusy(true); setError(null);
    try { const c = await api<{ id: string }>("/cases", { body: { text, domain: newDomain || undefined } }); router.push(`/app/cases/${c.id}`); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Could not create the case"); setBusy(false); }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <PageTitle title="Cases" sub="Consumer-rights and service cases across eight domains: intake, evidence, sources, options, a draft you approve, handoff, tracking and a verified outcome." />
      <ErrorNote error={error} />
      <section className="card" aria-labelledby="nc-h"><h2 id="nc-h" className="text-lg font-bold">Open a case</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_220px]">
          <div><label htmlFor="nc" className="label">What happened? Include dates, amounts, reference numbers and the company.</label>
            <textarea id="nc" className="input resize-y py-3" rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. My IndiGo flight 6E-2134 on 15 January 2026 was cancelled and they refused a refund of Rs 8,500. PNR: ABC123" maxLength={4000} /></div>
          <div><label htmlFor="nd" className="label">Domain</label>
            <select id="nd" className="input" value={newDomain} onChange={(e) => setNewDomain(e.target.value)}><option value="">Detect automatically</option>{doms.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}</select>
            <button className="btn-primary mt-3 w-full" disabled={busy || text.trim().length < 10} onClick={() => void create()}>{busy ? "Analysing…" : "Open case"}</button></div>
        </div>
        <div className="mt-4"><p className="mb-2 text-xs font-semibold text-muted">Examples (click to fill)</p>
          <ul className="flex flex-wrap gap-2">{doms.map((d) => <li key={d.id}><button className="min-h-[36px] rounded-full border border-line bg-soft px-3 text-xs font-semibold hover:border-indigo" onClick={() => { setText(EXAMPLES[d.id] ?? ""); setNewDomain(d.id); }}>{d.label}</button></li>)}</ul></div>
      </section>

      <section aria-labelledby="cl-h">
        <div className="mb-3 grid gap-2 sm:grid-cols-4"><h2 id="cl-h" className="sr-only">Your cases</h2>
          <div><label className="sr-only" htmlFor="cq">Search</label><input id="cq" className="input" placeholder="Search cases, providers…" value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} /></div>
          <div><label className="sr-only" htmlFor="cd">Domain</label><select id="cd" className="input" value={domain} onChange={(e) => { setDomain(e.target.value); setPage(0); }}><option value="">All domains</option>{doms.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}</select></div>
          <div><label className="sr-only" htmlFor="cs">Status</label><select id="cs" className="input" value={status} onChange={(e) => { setStatus(e.target.value); setPage(0); }}><option value="">Any status</option>{Object.keys(STATUS_TONE).map((s) => <option key={s} value={s}>{s.replaceAll("_", " ").toLowerCase()}</option>)}</select></div>
          <div><label className="sr-only" htmlFor="co">Sort</label><select id="co" className="input" value={sort} onChange={(e) => setSort(e.target.value)}><option value="updated">Recently updated</option><option value="created">Newest</option><option value="title">Title A–Z</option><option value="status">Status</option></select></div>
        </div>
        {rows === null ? <p className="text-muted" role="status">Loading…</p> : rows.length === 0 ? <Empty title="No cases match">Open one above, or run demo scenario A to see a case created from a mission.</Empty> : (
          <ul className="space-y-3">{rows.map((c) => (
            <li key={c.id}><Link href={`/app/cases/${c.id}`} className="card grid gap-3 p-5 hover:border-indigo md:grid-cols-[1fr_200px] md:items-center">
              <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><Tag tone={STATUS_TONE[c.status] ?? "soft"}>{c.status.replaceAll("_", " ").toLowerCase()}</Tag><Tag>{c.domain_label}</Tag>{c.overdue && <Tag tone="danger">follow-up overdue</Tag>}{c.missing > 0 && <Tag tone="indigo">{c.missing} fact(s) needed</Tag>}</div>
                <p className="mt-2 truncate text-base font-bold">{c.title}</p>
                <p className="text-xs text-muted">{c.provider ?? "—"}, {c.claimed_paise ? inr(c.claimed_paise) + " at stake, " : ""}stage {c.stage.replaceAll("_", " ").toLowerCase()}, updated {when(c.updated_at)}</p></div>
              <div><p className="mb-1 text-xs font-semibold text-muted">Analysis confidence</p><Meter value={c.confidence ?? 0} tone="indigo" label="Confidence" /></div>
            </Link></li>))}</ul>)}
        <div className="mt-4 flex items-center justify-between text-sm text-muted"><span>{total} case{total === 1 ? "" : "s"}</span>
          <div className="flex gap-2"><button className="btn-ghost" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button><button className="btn-ghost" disabled={(page + 1) * LIMIT >= total} onClick={() => setPage(page + 1)}>Next</button></div></div>
      </section>
      {radar && radar.items.length > 0 && (
        <section className="card" aria-labelledby="rd-h"><h2 id="rd-h" className="text-lg font-bold">Institution radar</h2><p className="text-sm text-muted">{radar.scope}</p>
          <div className="mt-3 overflow-x-auto"><table className="w-full min-w-[560px] text-sm"><thead><tr className="border-b border-line text-left text-muted"><th className="py-2 pr-3">Institution</th><th className="pr-3">Cases</th><th className="pr-3">Domains</th><th className="pr-3">At stake</th><th className="pr-3">Resolved / unresolved / open</th><th>Common issues</th></tr></thead>
            <tbody>{radar.items.map((r) => (<tr key={r.institution} className="border-b border-line"><td className="py-2 pr-3 font-semibold">{r.institution}</td><td className="pr-3">{r.cases}</td><td className="pr-3">{r.domains.join(", ")}</td><td className="pr-3">{r.claimed_paise ? inr(r.claimed_paise) : "—"}</td><td className="pr-3">{r.resolved} / {r.unresolved} / {r.open}</td><td>{Object.entries(r.issues).map(([k, n]) => `${k.replaceAll("_", " ")} (${n})`).join(", ")}</td></tr>))}</tbody></table></div></section>)}
    </div>
  );
}
