"use client";
import { useCallback, useEffect, useState, type ChangeEvent } from "react";
import { Empty, ErrorNote, PageTitle, Tag } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { when } from "@/lib/format";

type D = { id: string; filename: string; sha256: string; version: number; size: number; created_at: string; extracted: { booking_refs?: string[]; injection_suspected?: boolean; note?: string } };
export default function Vault() {
  const [items, setItems] = useState<D[]>([]);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => api<{ items: D[] }>("/documents").then((r) => setItems(r.items)).catch((e) => setError(e.message)), []);
  useEffect(() => { void load(); }, [load]);
  const upload = async (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (!f) return;
    const form = new FormData(); form.append("file", f);
    try { await api("/documents", { form }); setError(null); await load(); } catch (err) { setError(err instanceof ApiError ? err.message : "Upload failed"); }
    e.target.value = "";
  };
  const del = async (id: string) => { await api(`/documents/${id}`, { method: "DELETE" }); await load(); };
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageTitle title="Evidence Vault" sub="Upload tickets or receipts (text files, up to 2 MB). Each version is hashed. PDF text extraction is not implemented yet." />
      <ErrorNote error={error} />
      <label className="btn-primary cursor-pointer">Upload a document<input type="file" className="sr-only" onChange={(e) => void upload(e)} accept=".txt,.md,.csv,.pdf,.png,.jpg" /></label>
      {items.length === 0 ? <Empty title="Nothing stored yet" /> : (
        <ul className="space-y-3">{items.map((d) => (<li key={d.id} className="card"><div className="flex flex-wrap items-center justify-between gap-2">
          <div><p className="font-bold">{d.filename} <Tag>v{d.version}</Tag></p><p className="text-xs text-muted">{when(d.created_at)} · {d.size} bytes</p></div>
          <div className="flex gap-2"><a className="btn-ghost" href={`/api/v1/documents/${d.id}/download`}>Download</a><button className="btn-ghost" onClick={() => void del(d.id)}>Delete</button></div></div>
          <p className="mt-2 break-all text-xs text-muted">SHA-256 {d.sha256}</p>
          {d.extracted.booking_refs && d.extracted.booking_refs.length > 0 && <p className="mt-1 text-sm">References found: {d.extracted.booking_refs.join(", ")}</p>}
          {d.extracted.injection_suspected && <p className="mt-1 text-sm text-danger">This file contains instruction-like text. It is treated as data only and cannot approve or run anything.</p>}
          {d.extracted.note && <p className="mt-1 text-xs text-muted">{d.extracted.note}</p>}</li>))}</ul>)}
    </div>
  );
}
