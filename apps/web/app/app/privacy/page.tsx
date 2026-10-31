"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, PageTitle, Tag } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

type Key = { id: string; version: number; status: string; kek_id: string; created_at: string };
type Enc = { algorithm: string; scheme: string; kek_id: string; kek_source: string; production_mode: boolean; kms_integrated: boolean; key_versions: Key[]; encrypted: string[]; not_encrypted_at_application_layer: string[]; end_to_end: boolean };
type Summary = { counts: Record<string, number>; consents: Record<string, boolean>; encryption: Enc; retention: Record<string, string>; controls: string[] };
const CNT: [string, string, string][] = [["memory_items", "Memory items", "/app/memory"], ["documents", "Documents", "/app/vault"], ["missions", "Missions", "/app/history"], ["cases", "Cases", "/app/cases"], ["calls", "Voice calls", "/app/voice"]];

export default function Privacy() {
  const [s, setS] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => { try { setS(await api<Summary>("/privacy/summary")); } catch (e) { setError(e instanceof ApiError ? e.message : "Could not load"); } }, []);
  useEffect(() => { void load(); }, [load]);
  const rotate = async () => { setBusy(true); try { await api("/privacy/keys/rotate", { method: "POST" }); await load(); } catch (e) { setError(e instanceof ApiError ? e.message : "Rotation failed"); } finally { setBusy(false); } };
  const exportAll = async () => {
    try { const j = await api<unknown>("/privacy/export"); const url = URL.createObjectURL(new Blob([JSON.stringify(j, null, 2)], { type: "application/json" })); const a = document.createElement("a"); a.href = url; a.download = "redeem-export.json"; a.click(); URL.revokeObjectURL(url); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Export failed"); }
  };
  const e = s?.encryption;
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageTitle title="Privacy Center" sub="What REDEEM holds for you, how it is protected, and the controls that act on the real data." />
      <ErrorNote error={error} />
      <ul className="grid grid-cols-2 gap-3 md:grid-cols-5">{CNT.map(([k, l, href]) => (<li key={k}><Link href={href} className="card block !p-4 text-center hover:no-underline"><p className="glow-text text-3xl font-extrabold tabular-nums">{s ? s.counts[k] : "—"}</p><p className="mt-1 text-xs font-semibold uppercase tracking-wider text-muted">{l}</p></Link></li>))}</ul>
      <section className="card" aria-labelledby="enc-h">
        <div className="flex flex-wrap items-center justify-between gap-3"><h2 id="enc-h" className="text-lg font-bold">Encryption</h2>{e && <div className="flex gap-2"><Tag tone="teal">{e.algorithm}</Tag><Tag tone={e.production_mode ? "teal" : "amber"}>{e.production_mode ? "production key" : "development key"}</Tag><Tag tone="soft">not end-to-end</Tag></div>}</div>
        {e && (<div className="mt-3 grid gap-5 md:grid-cols-2">
          <div><p className="text-sm text-muted">{e.scheme}. Key-encryption key <span className="font-mono text-ink">{e.kek_id}</span> from {e.kek_source}. No KMS is integrated.</p>
            <p className="label mt-4">Your data-key versions</p>
            <ul className="space-y-1 text-sm">{e.key_versions.length ? e.key_versions.map((k) => <li key={k.id} className="flex flex-wrap items-center gap-2 rounded-lg bg-soft px-3 py-2"><span className="font-mono">v{k.version}</span><Tag tone={k.status === "active" ? "teal" : "soft"}>{k.status}</Tag><span className="text-muted">{k.created_at.slice(0, 10)}</span></li>) : <li className="text-muted">Created on first save.</li>}</ul>
            <button className="btn-ghost mt-3" disabled={busy} onClick={() => void rotate()}>Rotate my data key</button><p className="mt-1 text-xs text-muted">New writes use the new key; older data stays readable.</p></div>
          <div className="text-sm"><p className="font-semibold">Encrypted by the application</p><ul className="mt-1 list-disc pl-5 text-muted">{e.encrypted.map((x) => <li key={x}>{x}</li>)}</ul>
            <p className="mt-3 font-semibold">Not encrypted at the application layer</p><ul className="mt-1 list-disc pl-5 text-muted">{e.not_encrypted_at_application_layer.map((x) => <li key={x}>{x}</li>)}</ul></div></div>)}
      </section>
      <section className="grid gap-4 md:grid-cols-2">
        <div className="card"><h2 className="text-lg font-bold">Consent</h2><ul className="mt-2 space-y-2 text-sm">{s && ["voice_call", "call_recording", "memory_capture"].map((p) => (<li key={p} className="flex items-center justify-between gap-2 rounded-lg bg-soft px-3 py-2"><span className="font-mono">{p}</span><Tag tone={s.consents[p] ? "teal" : "soft"}>{s.consents[p] ? "granted" : "not granted"}</Tag></li>))}</ul><p className="mt-2 text-xs text-muted">Change memory capture in the <Link className="text-teal" href="/app/memory">Memory Center</Link>.</p></div>
        <div className="card"><h2 className="text-lg font-bold">Retention</h2><dl className="mt-2 space-y-2 text-sm">{s && Object.entries(s.retention).map(([k, v]) => <div key={k}><dt className="font-semibold capitalize">{k.replace("_", " ")}</dt><dd className="text-muted">{v}</dd></div>)}</dl></div>
      </section>
      <section className="card"><h2 className="text-lg font-bold">Your data</h2><p className="mt-1 text-sm text-muted">Export everything as JSON, or delete the account (this also destroys your encryption keys).</p>
        <div className="mt-3 flex flex-wrap gap-3"><button className="btn-primary" onClick={() => void exportAll()}>Export all my data</button><Link className="btn-ghost" href="/app/settings">Delete account…</Link></div></section>
    </div>
  );
}
