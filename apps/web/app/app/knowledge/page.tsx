"use client";
import { useEffect, useState } from "react";
import { Empty, ErrorNote, PageTitle, Tag } from "@/components/ui";
import { Meter } from "@/components/viz";
import { api, ApiError } from "@/lib/api";
import type { Source } from "@/lib/types";

type Stats = { chunks: number; by_domain_provenance: { domain: string; provenance: string; chunks: number }[] };
const DOMS = [["", "All domains"], ["travel", "Airline & travel"], ["banking", "Banking"], ["telecom", "Telecom"], ["ecommerce", "E-commerce"], ["housing", "Housing"], ["government", "Government"], ["healthcare", "Healthcare"], ["insurance", "Insurance"]];

export default function Knowledge() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [q, setQ] = useState(""); const [dom, setDom] = useState("");
  const [hits, setHits] = useState<Source[] | null>(null); const [note, setNote] = useState(""); const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null);
  useEffect(() => { api<Stats>("/knowledge/stats").then(setStats).catch(() => undefined); }, []);
  const search = async () => {
    setBusy(true); setError(null);
    try { const r = await api<{ items: Source[]; note: string }>("/knowledge/search", { body: { query: q, domains: dom ? [dom] : null, k: 8 } }); setHits(r.items); setNote(r.note); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Search failed"); } finally { setBusy(false); }
  };
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageTitle title="Knowledge search" sub="Retrieval over the regulatory and procedural material inherited from RECLAIM, with provenance and evidence scores on every passage." />
      <ErrorNote error={error} />
      {stats && <p className="rounded-xl bg-soft p-4 text-sm"><strong>{stats.chunks.toLocaleString("en-IN")} passages</strong> indexed. {stats.by_domain_provenance.map((x) => `${x.domain}: ${x.chunks} ${x.provenance === "scraped_official" ? "scraped from official pages" : "authored guides"}`).join(", ")}. <strong>Insurance: none</strong> — nothing is cited for it. REDEEM has not re-fetched or independently verified any of this.</p>}
      <form className="card flex flex-col gap-3 sm:flex-row" onSubmit={(e) => { e.preventDefault(); if (q.trim().length > 1) void search(); }} role="search">
        <label htmlFor="kq" className="sr-only">Search the knowledge base</label><input id="kq" className="input" placeholder="e.g. refund for a cancelled flight, delayed possession, billing complaint escalation" value={q} onChange={(e) => setQ(e.target.value)} />
        <label htmlFor="kd" className="sr-only">Domain</label><select id="kd" className="input sm:max-w-[200px]" value={dom} onChange={(e) => setDom(e.target.value)}>{DOMS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        <button className="btn-primary" disabled={busy || q.trim().length < 2}>{busy ? "Searching…" : "Search"}</button></form>
      {hits === null ? null : hits.length === 0 ? <Empty title="No passages found">Try different words or another domain.</Empty> : (<>
        <p className="text-xs text-muted">{note}</p>
        <ul className="space-y-4">{hits.map((s) => (<li key={s.id}><article className="card">
          <div className="flex flex-wrap items-center gap-2"><Tag tone={s.provenance === "scraped_official" ? "teal" : "amber"}>{s.provenance === "scraped_official" ? "scraped from an official page" : "authored guide (not official)"}</Tag><Tag>{s.authority || "unknown authority"}</Tag><Tag tone="soft">{s.domain ?? ""}</Tag><code className="text-xs">{s.id}</code></div>
          <h3 className="mt-2 font-bold">{s.title}</h3>{s.source_url && <a href={s.source_url} target="_blank" rel="noopener noreferrer" className="break-all text-xs font-semibold text-indigo underline">{s.source_url}</a>}
          <p className="mt-2 whitespace-pre-wrap text-sm text-muted">{s.passage}…</p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">{(["similarity", "authority", "legal_weight", "confidence"] as const).map((k) => <div key={k}><p className="text-xs text-muted">{k.replace("_", " ")}</p><Meter value={s.evidence_scores[k]} tone={k === "confidence" ? "indigo" : "teal"} label={k} /></div>)}</div>
        </article></li>))}</ul></>)}
    </div>
  );
}
