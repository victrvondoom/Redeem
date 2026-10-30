"use client";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type Mission } from "@/lib/api";
import { inr } from "@/lib/format";
import { Empty, Tag } from "./ui";

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
      <div className="flex flex-wrap items-center gap-2"><h2 id="alt-h" className="text-lg font-bold">Alternative flights</h2><Tag tone="amber">fixture data · read-only</Tag></div>
      <p className="mt-1 text-sm text-muted">Gathered in parallel with the policy and calendar reads. REDEEM lists options; it does not book a replacement.</p>
      <ul className="mt-3 divide-y divide-line text-sm">{alts.map((a) => (
        <li key={a.flight} className="flex flex-wrap items-center justify-between gap-2 py-2"><span><strong>{a.flight}</strong> · {a.route} · {a.departs}</span>
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
        <button className={`badge ${cat === "" ? "bg-deep text-white" : "bg-soft text-muted"}`} onClick={() => setCat("")}>All ({items.length})</button>
        {cats.map((c) => <button key={c} title={CAT_HELP[c]} className={`badge ${cat === c ? "bg-deep text-white" : "bg-soft text-muted"}`} onClick={() => setCat(c)}>{c.replaceAll("_", " ").toLowerCase()}</button>)}</div>
      {shown.length === 0 ? <div className="mt-3"><Empty title="No evidence yet" /></div> : (
        <ul className="mt-3 space-y-2">{shown.map((e) => (
          <li key={e.id} className="rounded-xl border border-line p-3 text-sm"><div className="flex flex-wrap items-center gap-2"><Tag tone={CAT_TONE[e.category] ?? "soft"}>{e.category.replaceAll("_", " ")}</Tag><strong>{e.title}</strong></div>
            <p className="mt-1 text-xs text-muted">{e.source} · {e.timestamp?.slice(0, 19).replace("T", " ")} UTC · {e.verification_status.replaceAll("_", " ").toLowerCase()} · <code>{e.id}</code> · hash <code>{e.content_hash.slice(0, 12)}</code></p></li>))}</ul>)}
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
      <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Filter by agent"><button className={`badge ${who === "" ? "bg-deep text-white" : "bg-soft text-muted"}`} onClick={() => setWho("")}>All</button>
        {roles.map((r) => <button key={r} className={`badge ${who === r ? "bg-deep text-white" : "bg-soft text-muted"}`} onClick={() => setWho(r)}>{r}</button>)}</div>
      <ul className="mt-3 space-y-1 text-sm">{shown.map((i) => (<li key={i.seq} className="flex gap-3"><span className="w-28 shrink-0 font-semibold">{i.agent}</span><span className="text-muted">{i.kind.replaceAll("_", " ")}</span></li>))}</ul>
    </section>
  );
}
