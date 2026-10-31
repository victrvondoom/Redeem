"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Empty, ErrorNote, PageTitle, Tag } from "@/components/ui";
import { Meter } from "@/components/viz";
import { api, ApiError } from "@/lib/api";
import { when } from "@/lib/format";
import type { Fact } from "@/lib/types";

type D = { id: string; filename: string; sha256: string; version: number; size: number; created_at: string; doc_type: string | null; domain: string | null; case_id: string | null; ocr_status: string | null; page_count: number | null;
  strength: { score: number; explanation: string }; relevance: { relevant: boolean; reason: string }; near_duplicate_of: string | null; fact_count: number; extracted: { booking_refs?: string[]; injection_suspected?: boolean } };
type Detail = D & { text: string; facts: Fact[]; versions: { id: string; version: number; sha256: string; created_at: string }[]; supports_claims: { claim: string; status: string; case_id: string }[] };
const TYPES = ["", "ticket", "booking", "bill", "invoice", "receipt", "statement", "policy", "rejection_letter", "notice", "correspondence", "agreement", "medical_bill", "discharge_summary", "application", "id_proof", "screenshot", "other"];
const DOMS = ["", "travel", "banking", "insurance", "telecom", "ecommerce", "housing", "government", "healthcare"];

export default function Vault() {
  const [items, setItems] = useState<D[]>([]); const [total, setTotal] = useState(0); const [error, setError] = useState<string | null>(null); const [notice, setNotice] = useState<string | null>(null);
  const [q, setQ] = useState(""); const [dtype, setDtype] = useState(""); const [domain, setDomain] = useState(""); const [sort, setSort] = useState("created"); const [uploadDomain, setUploadDomain] = useState("");
  const [detail, setDetail] = useState<Detail | null>(null); const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const load = useCallback(async () => {
    const p = new URLSearchParams({ sort, limit: "100" }); if (q) p.set("q", q); if (dtype) p.set("doc_type", dtype); if (domain) p.set("domain", domain);
    try { const r = await api<{ items: D[]; total: number }>(`/documents?${p}`); setItems(r.items); setTotal(r.total); } catch (e) { setError(e instanceof Error ? e.message : "Failed"); }
  }, [q, dtype, domain, sort]);
  useEffect(() => { const h = setTimeout(() => void load(), 200); return () => clearTimeout(h); }, [load]);
  const upload = async (f: File) => {
    const form = new FormData(); form.append("file", f); setBusy(true); setError(null); setNotice(null);
    try { const r = await api<D & { ingest: { duplicate?: boolean; note?: string; near_duplicate_of?: string } }>(`/documents${uploadDomain ? `?domain=${uploadDomain}` : ""}`, { form });
      setNotice(r.ingest.duplicate ? (r.ingest.note ?? "Duplicate") : `Stored ${r.filename}: ${r.doc_type?.replaceAll("_", " ") ?? "other"}${r.ocr_status ? ` (${r.ocr_status.replaceAll("_", " ")})` : ""}${r.ingest.near_duplicate_of ? " · near-duplicate of an existing file" : ""}.`); await load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Upload failed"); } finally { setBusy(false); }
  };
  const open = async (id: string) => { try { setDetail(await api<Detail>(`/documents/${id}`)); } catch (e) { setError(e instanceof Error ? e.message : "Failed"); } };
  const del = async (id: string) => { if (!confirm("Delete this file and its stored bytes?")) return; await api(`/documents/${id}`, { method: "DELETE" }); setDetail(null); await load(); };
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageTitle title="Evidence Vault" sub="Every document is hashed, versioned, classified, scored for relevance and strength, and mined for facts with their source location. Text and PDF are read; images are stored but OCR is not available." />
      <ErrorNote error={error} />{notice && <p role="status" className="rounded-xl bg-teal-soft px-4 py-3 text-sm font-medium text-teal">{notice}</p>}
      <section className="card flex flex-col gap-3 sm:flex-row sm:items-end"><div className="flex-1"><label className="label" htmlFor="ud">Upload into domain (improves relevance scoring)</label><select id="ud" className="input" value={uploadDomain} onChange={(e) => setUploadDomain(e.target.value)}>{DOMS.map((d) => <option key={d} value={d}>{d || "No domain"}</option>)}</select></div>
        <div><input ref={fileRef} type="file" className="sr-only" aria-label="Choose a file" accept=".txt,.md,.csv,.pdf,.png,.jpg,.jpeg" onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); e.target.value = ""; }} /><button className="btn-primary" disabled={busy} onClick={() => fileRef.current?.click()}>Upload document</button></div></section>
      <div className="grid gap-2 sm:grid-cols-4"><div><label className="sr-only" htmlFor="vq">Search</label><input id="vq" className="input" placeholder="Search names and contents" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        <div><label className="sr-only" htmlFor="vt">Type</label><select id="vt" className="input" value={dtype} onChange={(e) => setDtype(e.target.value)}>{TYPES.map((t) => <option key={t} value={t}>{t ? t.replaceAll("_", " ") : "Any type"}</option>)}</select></div>
        <div><label className="sr-only" htmlFor="vd">Domain</label><select id="vd" className="input" value={domain} onChange={(e) => setDomain(e.target.value)}>{DOMS.map((d) => <option key={d} value={d}>{d || "Any domain"}</option>)}</select></div>
        <div><label className="sr-only" htmlFor="vs">Sort</label><select id="vs" className="input" value={sort} onChange={(e) => setSort(e.target.value)}><option value="created">Newest</option><option value="strength">Strongest evidence</option><option value="name">Name</option></select></div></div>
      <div className="grid gap-6 lg:grid-cols-[1fr_1.1fr]">
        <section aria-label="Documents">{items.length === 0 ? <Empty title="No documents match">Upload a ticket, bill or letter, or open a case and attach evidence there.</Empty> : (
          <ul className="space-y-2">{items.map((d) => (<li key={d.id}><button onClick={() => void open(d.id)} className={`card w-full p-4 text-left hover:border-indigo ${detail?.id === d.id ? "border-indigo" : ""}`}>
            <div className="flex flex-wrap items-center gap-2"><strong className="truncate">{d.filename}</strong><Tag>v{d.version}</Tag><Tag tone="indigo">{d.doc_type?.replaceAll("_", " ") ?? "other"}</Tag>{d.case_id && <Tag tone="teal">in a case</Tag>}{d.extracted.injection_suspected && <Tag tone="danger">instruction-like text</Tag>}</div>
            <p className="mt-1 text-xs text-muted">{when(d.created_at)} · {d.size.toLocaleString("en-IN")} bytes · {d.fact_count} facts{d.ocr_status ? ` · ${d.ocr_status.replaceAll("_", " ")}` : ""}</p><div className="mt-2"><Meter value={d.strength?.score ?? 0} tone={(d.strength?.score ?? 0) >= 0.35 ? "teal" : "amber"} label="Evidence strength" /></div></button></li>))}</ul>)}
          <p className="mt-3 text-xs text-muted">{total} document{total === 1 ? "" : "s"}</p></section>
        <section aria-label="Document detail" className="lg:sticky lg:top-6 lg:self-start">{!detail ? <Empty title="Select a document">Preview, extracted facts with their source, versions and the claims it supports appear here.</Empty> : (
          <div className="card space-y-4"><div className="flex flex-wrap items-start justify-between gap-2"><div><h2 className="font-bold">{detail.filename}</h2><p className="break-all text-xs text-muted">sha256 {detail.sha256}</p></div>
            <div className="flex gap-2"><a className="btn-ghost" href={`/api/v1/documents/${detail.id}/download`}>Download</a><button className="btn-ghost text-danger" onClick={() => void del(detail.id)}>Delete</button></div></div>
            <div><p className="text-xs font-semibold text-muted">Evidence strength</p><Meter value={detail.strength?.score ?? 0} label="Strength" /><p className="mt-1 text-xs text-muted">{detail.strength?.explanation}</p><p className="mt-1 text-xs">{detail.relevance?.relevant ? "Relevant." : "Not relevant."} {detail.relevance?.reason}</p></div>
            {detail.facts.length > 0 && <div><p className="text-xs font-semibold text-muted">Extracted facts → source</p><ul className="mt-1 space-y-1 text-sm">{detail.facts.filter((f) => f.kind !== "provider").slice(0, 12).map((f, i) => <li key={i}><Tag>{f.kind.replaceAll("_", " ")}</Tag> <strong>{f.display}</strong>{f.quote && <span className="block text-xs text-muted">p.{f.page ?? 1}: {f.quote}</span>}</li>)}</ul></div>}
            {detail.supports_claims.length > 0 && <div><p className="text-xs font-semibold text-muted">Supports claims</p><ul className="mt-1 text-sm">{detail.supports_claims.map((c, i) => <li key={i}><Tag tone="teal">{c.status.toLowerCase()}</Tag> {c.claim} <Link className="text-xs text-indigo underline" href={`/app/cases/${c.case_id}`}>case</Link></li>)}</ul></div>}
            {detail.versions.length > 1 && <div><p className="text-xs font-semibold text-muted">Version history</p><ul className="mt-1 text-xs text-muted">{detail.versions.map((v) => <li key={v.id}>v{v.version} · {v.sha256} · {when(v.created_at)}</li>)}</ul></div>}
            <div><p className="text-xs font-semibold text-muted">Extracted text</p><pre className="mt-1 max-h-72 overflow-auto whitespace-pre-wrap rounded-xl bg-soft p-3 text-xs">{detail.text || (detail.ocr_status ? `No text: ${detail.ocr_status.replaceAll("_", " ")}.` : "No text extracted.")}</pre></div></div>)}</section>
      </div>
    </div>
  );
}
