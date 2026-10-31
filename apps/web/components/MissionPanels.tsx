"use client";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type Mission } from "@/lib/api";
import { inr } from "@/lib/format";
import { Empty, Tag } from "./ui";
import { Dag, type TaskNode } from "./viz";

type Evidence = { id: string; category: string; title: string; source: string; timestamp: string | null; content_hash: string; verification_status: string; action_id: string | null };
type AgentMsg = { seq: number; agent: string; kind: string; at: string };

const CAT_TONE: Record<string, "teal" | "indigo" | "amber" | "danger" | "soft"> = {
  DATABASE_VERIFIED: "teal", PROVIDER_CONFIRMED: "indigo", USER_PROVIDED: "soft", INFERRED: "amber", UNVERIFIED: "danger",
};
const CAT_HELP: Record<string, string> = {
  DATABASE_VERIFIED: "Independently read back from the system of record",
  PROVIDER_CONFIRMED: "Returned by the provider (an acknowledgement, not proof)",
  USER_PROVIDED: "Supplied or approved by you",
  INFERRED: "Derived by REDEEM's rules, not independently confirmed",
  UNVERIFIED: "Insufficient or failed evidence",
};

export function ControlBar({ m, busy, onAct, selectedIds }: { m: Mission; busy: boolean; onAct: (fn: () => Promise<unknown>) => void; selectedIds: string[] }) {
  const id = m.id;
  const final = ["VERIFIED", "PARTIALLY_VERIFIED", "FAILED", "CANCELLED"].includes(m.status);
  if (final) return null;
  return (
    <section className="card flex flex-wrap items-center gap-2 p-4" aria-label="Mission control">
      <span className="mr-2 text-sm font-semibold">Control</span>
      {m.paused ? <button className="btn-teal" disabled={busy} onClick={() => onAct(() => api(`/missions/${id}/resume`, { method: "POST" }))}>Resume</button>
        : <button className="btn-ghost" disabled={busy} onClick={() => onAct(() => api(`/missions/${id}/pause`, { method: "POST" }))}>Pause</button>}
      {m.status === "NEEDS_APPROVAL" && <button className="btn-ghost" disabled={busy || selectedIds.length === 0}
        onClick={() => onAct(() => api(`/missions/${id}/reject`, { body: { action_ids: selectedIds, reason: "rejected by user" } }))}>Reject selected</button>}
      <button className="btn-ghost" disabled={busy || m.escalated} onClick={() => onAct(() => api(`/missions/${id}/escalate`, { method: "POST" }))}>{m.escalated ? "Escalated to a human" : "Escalate to a human"}</button>
      {m.paused && <Tag tone="amber">paused — nothing will run</Tag>}
      {m.escalated && <Tag tone="danger">needs human review</Tag>}
    </section>
  );
}

export function Alternatives({ m, lang }: { m: Mission; lang: string }) {
  const alts = m.plan.reads?.alternatives;
  if (!alts?.length) return null;
  return (
    <section className="card" aria-labelledby="alt-h">
      <div className="flex flex-wrap items-center gap-2"><h2 id="alt-h" className="text-lg font-bold">Alternative flights</h2><Tag tone="amber">fixture data, read-only</Tag></div>
      <p className="mt-1 text-sm text-muted">Gathered in parallel with the policy and calendar reads. REDEEM lists options; it does not book a replacement.</p>
      <ul className="mt-3 divide-y divide-line text-sm">{alts.map((a) => (
        <li key={a.flight} className="flex flex-wrap items-center justify-between gap-2 py-2"><span><strong>{a.flight}</strong>, {a.route}, {a.departs}</span>
          <span className="flex items-center gap-2">{inr(a.price_paise, lang)}{a.bookable ? <Tag tone="teal">{a.seats} seats</Tag> : <Tag tone="danger">sold out</Tag>}</span></li>))}</ul>
    </section>
  );
}

export function EvidenceCenter({ missionId, refreshKey }: { missionId: string; refreshKey: string }) {
  const [items, setItems] = useState<Evidence[]>([]);
  const [unc, setUnc] = useState<string[]>([]);
  const [cat, setCat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => api<{ items: Evidence[]; remaining_uncertainty: string[] }>(`/missions/${missionId}/evidence`)
    .then((r) => { setItems(r.items); setUnc(r.remaining_uncertainty); }).catch((e) => setError(e instanceof ApiError ? e.message : "Evidence unavailable")), [missionId]);
  useEffect(() => { void load(); }, [load, refreshKey]);
  const download = async (fmt: "json" | "md") => {
    const res = await fetch(`/api/v1/missions/${missionId}/report?format=${fmt}`, { credentials: "same-origin" });
    const blob = new Blob([await res.text()], { type: fmt === "md" ? "text/markdown" : "application/json" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `redeem-report-${missionId}.${fmt}`; a.click(); URL.revokeObjectURL(a.href);
  };
  const shown = cat ? items.filter((i) => i.category === cat) : items;
  const cats = Array.from(new Set(items.map((i) => i.category)));
  return (
    <section className="card" aria-labelledby="ev-h">
      <div className="flex flex-wrap items-center justify-between gap-2"><h2 id="ev-h" className="text-lg font-bold">Evidence Center</h2>
        <div className="flex gap-2"><button className="btn-ghost" onClick={() => void download("md")}>Report (readable)</button><button className="btn-ghost" onClick={() => void download("json")}>Report (JSON)</button></div></div>
      {error && <p role="alert" className="mt-2 text-sm text-danger">{error}</p>}
      <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Filter by trust category">
        <button className={`badge ${cat === "" ? "bg-teal text-deep" : "bg-soft text-muted"}`} onClick={() => setCat("")}>All ({items.length})</button>
        {cats.map((c) => <button key={c} title={CAT_HELP[c]} className={`badge ${cat === c ? "bg-teal text-deep" : "bg-soft text-muted"}`} onClick={() => setCat(c)}>{c.replaceAll("_", " ").toLowerCase()}</button>)}</div>
      {shown.length === 0 ? <div className="mt-3"><Empty title="No evidence yet" /></div> : (
        <ul className="mt-3 space-y-2">{shown.map((e) => (
          <li key={e.id} className="rounded-xl border border-line p-3 text-sm"><div className="flex flex-wrap items-center gap-2"><Tag tone={CAT_TONE[e.category] ?? "soft"}>{e.category.replaceAll("_", " ")}</Tag><strong>{e.title}</strong></div>
            <p className="mt-1 text-xs text-muted">{e.source}, {e.timestamp?.slice(0, 19).replace("T", " ")} UTC, {e.verification_status.replaceAll("_", " ").toLowerCase()}, <code>{e.id}</code>, hash <code>{e.content_hash.slice(0, 12)}</code></p></li>))}</ul>)}
      {unc.length > 0 && <div className="mt-4 rounded-xl bg-amber-soft p-4 text-sm"><p className="font-semibold">Remaining uncertainty</p><ul className="mt-1 list-disc pl-5">{unc.map((u) => <li key={u}>{u.replaceAll("_", " ")}</li>)}</ul></div>}
    </section>
  );
}

export function AgentActivity({ missionId, refreshKey }: { missionId: string; refreshKey: string }) {
  const [items, setItems] = useState<AgentMsg[]>([]);
  const [who, setWho] = useState("");
  useEffect(() => { api<{ items: AgentMsg[] }>(`/missions/${missionId}/agents`).then((r) => setItems(r.items)).catch(() => undefined); }, [missionId, refreshKey]);
  const roles = Array.from(new Set(items.map((i) => i.agent.split(":")[0])));
  const shown = who ? items.filter((i) => i.agent.startsWith(who)) : items;
  if (items.length === 0) return null;
  return (
    <section className="card" aria-labelledby="ag-h"><h2 id="ag-h" className="text-lg font-bold">Agent activity</h2>
      <p className="mt-1 text-sm text-muted">Each role has least-privilege capabilities; only the executor can dispatch an action.</p>
      <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Filter by agent"><button className={`badge ${who === "" ? "bg-teal text-deep" : "bg-soft text-muted"}`} onClick={() => setWho("")}>All</button>
        {roles.map((r) => <button key={r} className={`badge ${who === r ? "bg-teal text-deep" : "bg-soft text-muted"}`} onClick={() => setWho(r)}>{r}</button>)}</div>
      <ul className="mt-3 space-y-1 text-sm">{shown.map((i) => (<li key={i.seq} className="flex gap-3"><span className="w-28 shrink-0 font-semibold">{i.agent}</span><span className="text-muted">{i.kind.replaceAll("_", " ")}</span></li>))}</ul>
    </section>
  );
}

// ---------------------------------------------------------------- task DAG, browser sessions, commands (inherited RESOLVE surfaces)

export function TaskGraph({ tasks }: { tasks: TaskNode[] }) {
  const [sel, setSel] = useState<TaskNode | null>(null);
  if (!tasks?.length) return null;
  const rev = Math.max(...tasks.map((t) => t.revision));
  const cur = tasks.filter((t) => t.revision === rev);
  const count = (s: string) => cur.filter((t) => t.status === s).length;
  return (
    <section className="card" aria-labelledby="dag-h">
      <div className="flex flex-wrap items-center justify-between gap-2"><h2 id="dag-h" className="text-lg font-bold">Task graph</h2>
        <p className="text-xs text-muted">revision {rev}, {cur.length} tasks, {count("DONE")} done, {count("RUNNING")} running, {count("FAILED")} failed, {count("SKIPPED")} skipped, {count("QUEUED")} queued</p></div>
      <p className="mt-1 text-sm text-muted">Every node has an owner role, dependencies, a timeout and a retry budget, and is persisted. Reads can run concurrently; writes are serialised and gated on their dependencies.</p>
      <div className="mt-3"><Dag tasks={tasks} selected={sel?.id} onSelect={setSel} /></div>
      {sel && (<div className="mt-3 rounded-xl bg-soft p-4 text-sm"><p className="font-semibold">{sel.kind} <Tag>{sel.owner}</Tag> <Tag tone={sel.status === "DONE" ? "teal" : sel.status === "FAILED" ? "danger" : "amber"}>{sel.status.toLowerCase()}</Tag> <Tag>{sel.mode}</Tag></p>
        <p className="mt-1 text-xs text-muted">attempts {sel.attempts}/{sel.retry_budget + 1}{sel.error ? `, error: ${sel.error}` : ""}</p>
        {Object.keys(sel.output).length > 0 && <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(sel.output, null, 1)}</pre>}</div>)}
    </section>
  );
}

type Snap = { id: string; phase: string; label: string; url: string; title: string; dom_sha: string; aria_sha: string; screenshot_sha: string; screenshot_url: string; fused: { api_sha: string | null; elements: number } };
type Sess = { id: string; status: string; origins: string[]; blocked_requests: string[]; user_action: { reason: string } | null; note: string | null; started_at: string; snapshots: Snap[] };

export function BrowserPanel({ missionId, refreshKey }: { missionId: string; refreshKey: string }) {
  const [items, setItems] = useState<Sess[]>([]);
  const [shot, setShot] = useState<Snap | null>(null);
  useEffect(() => { api<{ items: Sess[] }>(`/browser/sessions?mission_id=${missionId}`).then((r) => setItems(r.items)).catch(() => undefined); }, [missionId, refreshKey]);
  if (!items.length) return null;
  return (
    <section className="card" aria-labelledby="br-h">
      <div className="flex flex-wrap items-center gap-2"><h2 id="br-h" className="text-lg font-bold">Browser sessions</h2><Tag tone="amber">real Chromium, simulated apps</Tag></div>
      <p className="mt-1 text-sm text-muted">A fresh browser context per run, restricted to the simulated CRM, report store and outbox on loopback. Each action is recorded before and after; the page&apos;s own success message is never trusted.</p>
      <ul className="mt-3 space-y-3">{items.map((s) => (
        <li key={s.id} className="rounded-xl border border-line p-4 text-sm">
          <div className="flex flex-wrap items-center gap-2"><Tag tone={s.status === "DONE" ? "teal" : s.status === "USER_ACTION_REQUIRED" ? "amber" : "danger"}>{s.status.replaceAll("_", " ").toLowerCase()}</Tag><code className="text-xs">{s.id}</code>
            <span className="text-xs text-muted">{s.blocked_requests.length} blocked outside request(s)</span>{s.user_action && <Tag tone="amber">waiting for you: {s.user_action.reason}</Tag>}</div>
          {s.note && <p className="mt-1 text-xs text-muted">Adapted: {s.note}</p>}
          <ul className="mt-2 grid gap-2 sm:grid-cols-2">{s.snapshots.map((x) => (
            <li key={x.id}><button onClick={() => setShot(x)} className="w-full rounded-lg bg-soft p-2 text-left hover:ring-2 hover:ring-indigo"><span className="flex items-center gap-2"><Tag tone={x.phase === "after" ? "teal" : x.phase === "before" ? "amber" : "indigo"}>{x.phase}</Tag><span className="truncate text-xs font-semibold">{x.label}</span></span>
              <span className="mt-1 block text-[11px] text-muted">dom {x.dom_sha.slice(0, 8)}, aria {x.aria_sha.slice(0, 8)}, shot {x.screenshot_sha.slice(0, 8)}, {x.fused.elements} elements</span></button></li>))}</ul>
        </li>))}</ul>
      {shot && (<div className="mt-4 rounded-xl border border-line p-3"><div className="flex items-center justify-between"><p className="text-sm font-semibold">{shot.phase}, {shot.label}</p><button className="text-xs underline" onClick={() => setShot(null)}>Close</button></div>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={shot.screenshot_url} alt={`Screenshot: ${shot.label}`} className="mt-2 w-full rounded-lg border border-line" />
        <p className="mt-1 break-all text-[11px] text-muted">{shot.url}, state fusion: URL + DOM text hash + ARIA tree hash + screenshot hash + API state hash {shot.fused.api_sha ? shot.fused.api_sha.slice(0, 10) : "n/a"}</p></div>)}
    </section>
  );
}

const CMD_CHIPS = ["what happened", "explain", "pause", "resume", "undo", "stop"];
export function CommandBox({ missionId, onDone }: { missionId: string; onDone: () => void }) {
  const [text, setText] = useState("");
  const [log, setLog] = useState<{ you: string; reply: string; ok: boolean }[]>([]);
  const [busy, setBusy] = useState(false);
  const send = async (t: string) => {
    if (!t.trim()) return;
    setBusy(true);
    try { const r = await api<{ message: string; ok: boolean }>(`/missions/${missionId}/utterance`, { body: { text: t } }); setLog((l) => [{ you: t, reply: r.message, ok: r.ok }, ...l].slice(0, 6)); setText(""); onDone(); }
    catch (e) { setLog((l) => [{ you: t, reply: e instanceof ApiError ? e.message : "Failed", ok: false }, ...l]); } finally { setBusy(false); }
  };
  return (
    <section className="card" aria-labelledby="cmd-h"><h2 id="cmd-h" className="text-lg font-bold">Talk to this mission</h2>
      <p className="mt-1 text-sm text-muted">Type (or dictate) <em>stop, pause, resume, change this, undo, explain, what happened</em> — English, Hindi, Hinglish, Tamil, Telugu keywords work. Every reply states what actually happened.</p>
      <form className="mt-3 flex flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); void send(text); }}><label htmlFor="cmd" className="sr-only">Command</label>
        <input id="cmd" className="input" placeholder="e.g. actually, use the other contact — or: kya hua" value={text} onChange={(e) => setText(e.target.value)} /><button className="btn-primary" disabled={busy || !text.trim()}>Send</button></form>
      <div className="mt-2 flex flex-wrap gap-2">{CMD_CHIPS.map((c) => <button key={c} className="badge min-h-[32px] bg-soft text-muted hover:text-ink" disabled={busy} onClick={() => void send(c)}>{c}</button>)}</div>
      {log.length > 0 && <ul className="mt-3 space-y-2 text-sm" aria-live="polite">{log.map((l, i) => <li key={i} className="rounded-xl bg-soft p-3"><p className="text-xs text-muted">you: {l.you}</p><p className={l.ok ? "" : "text-danger"}>{l.reply}</p></li>)}</ul>}
    </section>
  );
}
