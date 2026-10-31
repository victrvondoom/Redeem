"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Empty, ErrorNote, PageTitle, Tag } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { when } from "@/lib/format";

type Inv = { total_files: number; total_bytes: number; truncated: boolean; scope: string; files?: { path: string; size: number; sha256?: string; mtime?: string }[] };
type Plan = { plan_id: string; dry_run: boolean; moves: { src: string; dst: string; kept: string; size: number; sha256: string }[]; note: string };
type Op = { op_id: string; status: string; created_at: string; verification: { status: string; checks: { ok: boolean; origin_absent?: boolean }[] } | null };

export default function Files() {
  const [inv, setInv] = useState<Inv | null>(null); const [dups, setDups] = useState<{ groups: { sha256: string; files?: string[]; paths?: string[] }[] } | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null); const [ops, setOps] = useState<Op[]>([]); const [error, setError] = useState<string | null>(null); const [notice, setNotice] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLInputElement>(null);
  const load = useCallback(async () => {
    try { setInv(await api<Inv>("/files")); setDups(await api("/files/duplicates")); setOps((await api<{ operations: Op[] }>("/files/operations")).operations); } catch (e) { setError(e instanceof Error ? e.message : "Failed"); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const run = async (fn: () => Promise<unknown>, ok: string) => { setBusy(true); setError(null); setNotice(null); try { await fn(); setNotice(ok); await load(); } catch (e) { setError(e instanceof ApiError ? e.message : "Failed"); await load(); } finally { setBusy(false); } };
  const upload = (f: File) => { const form = new FormData(); form.append("file", f); return run(() => api("/files/upload", { form }), `Added ${f.name} to your sandbox.`); };
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageTitle title="Files" sub="A private, sandboxed file workflow inherited from RESOLVE: find duplicates by content hash, preview a dry-run plan, apply it with a hash re-check, and undo — each step verified." />
      <ErrorNote error={error} />{notice && <p role="status" className="rounded-xl bg-teal-soft px-4 py-3 text-sm font-medium text-teal">{notice}</p>}
      <section className="card flex flex-wrap items-center justify-between gap-3"><div><p className="font-semibold">{inv ? `${inv.total_files} file(s), ${inv.total_bytes.toLocaleString("en-IN")} bytes` : "Loading…"}</p><p className="text-xs text-muted">{inv?.scope}</p></div>
        <div><input ref={ref} type="file" className="sr-only" aria-label="Add a file" onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); e.target.value = ""; }} /><button className="btn-primary" disabled={busy} onClick={() => ref.current?.click()}>Add a file</button></div></section>
      <section className="card" aria-labelledby="fl-h"><h2 id="fl-h" className="text-lg font-bold">Inventory</h2>{inv?.files?.length ? <ul className="mt-3 divide-y divide-line text-sm">{inv.files.map((f) => (<li key={f.path} className="flex flex-wrap items-center justify-between gap-2 py-2"><span className="font-mono text-xs">{f.path}</span><span className="flex items-center gap-3 text-xs text-muted">{f.size.toLocaleString("en-IN")} B {f.sha256 && <code>{f.sha256.slice(0, 10)}…</code>}<a className="font-semibold text-indigo underline" href={`/api/v1/files/download?path=${encodeURIComponent(f.path)}`}>download</a></span></li>))}</ul> : <div className="mt-3"><Empty title="Your sandbox is empty">Add a few files — two identical ones will show up as duplicates.</Empty></div>}</section>
      <section className="card" aria-labelledby="dp-h"><h2 id="dp-h" className="text-lg font-bold">Duplicates</h2>
        {dups && dups.groups.length ? <ul className="mt-3 space-y-2 text-sm">{dups.groups.map((g) => <li key={g.sha256} className="rounded-xl bg-soft p-3"><Tag tone="amber">{(g.files ?? g.paths ?? []).length} identical files</Tag> <code className="text-xs">{g.sha256.slice(0, 14)}…</code><p className="mt-1 font-mono text-xs">{(g.files ?? g.paths ?? []).join(" ,  ")}</p></li>)}</ul> : <p className="mt-2 text-sm text-muted">No duplicates found.</p>}
        <button className="btn-ghost mt-4" disabled={busy || !dups?.groups.length} onClick={() => void run(async () => setPlan(await api<Plan>("/files/plan", { method: "POST" })), "Dry-run plan created. Nothing has moved.")}>Create dry-run plan</button></section>
      {plan && (<section className="card border-indigo" aria-labelledby="pl-h"><h2 id="pl-h" className="text-lg font-bold">Plan {plan.plan_id} <Tag tone="amber">dry run</Tag></h2><p className="text-sm text-muted">{plan.note}</p>
        <ul className="mt-3 space-y-1 text-sm">{plan.moves.map((m) => <li key={m.src}>Move <code>{m.src}</code> → <code>{m.dst}</code> (keeps <code>{m.kept}</code>)</li>)}</ul>
        <button className="btn-primary mt-4" disabled={busy} onClick={() => void run(async () => { await api("/files/apply", { body: { plan_id: plan.plan_id } }); setPlan(null); }, "Applied and verified by re-hashing.")}>Apply plan</button></section>)}
      <section className="card" aria-labelledby="op-h"><h2 id="op-h" className="text-lg font-bold">Operations &amp; undo</h2>
        {ops.length ? <ul className="mt-3 space-y-2 text-sm">{ops.map((o) => (<li key={o.op_id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line p-3"><span><code className="text-xs">{o.op_id}</code> <Tag tone={o.status === "CONFIRMED" ? "teal" : o.status === "UNDONE" ? "soft" : "amber"}>{o.status.toLowerCase()}</Tag><span className="ml-2 text-xs text-muted">{when(o.created_at)}, {o.verification?.checks?.length ?? 0} file(s) verified</span></span>
          {o.status === "CONFIRMED" && <button className="btn-ghost" disabled={busy} onClick={() => void run(() => api("/files/undo", { body: { op_id: o.op_id } }), "Undone; originals restored and verified.")}>Undo</button>}</li>))}</ul> : <p className="mt-2 text-sm text-muted">No operations yet.</p>}</section>
    </div>
  );
}
