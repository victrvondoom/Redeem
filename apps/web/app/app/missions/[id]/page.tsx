"use client";
import { use, useCallback, useEffect, useMemo, useState } from "react";
import { AgentActivity, Alternatives, ControlBar, EvidenceCenter } from "@/components/MissionPanels";
import { Empty, ErrorNote, StatusBadge, Tag } from "@/components/ui";
import { api, ApiError, type LedgerEvent, type Mission, type PlanAction } from "@/lib/api";
import { inr, TERMINAL, when } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

const STEPS = ["INTENT_CAPTURED", "CLASSIFIED", "DISCOVERING", "NEEDS_APPROVAL", "AUTHORIZED", "EXECUTING", "VERIFIED"];
const KIND_LABEL: Record<string, string> = {
  refund_request: "Refund request to airline desk", hotel_change_request: "Date-change request to hotel desk", reserve_stock: "Reserve stock for customer",
  calendar_update: "Correct calendar event", notify_contact: "Prepare family message (draft, not sent)", crm_followup: "Schedule CRM follow-up", prepare_case: "Prepare case record (not filed externally)",
};

export default function MissionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { lang, t } = useI18n();
  const [m, setM] = useState<Mission | null>(null);
  const [events, setEvents] = useState<LedgerEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [correction, setCorrection] = useState("");
  const [dateVal, setDateVal] = useState("");
  const [confirmText, setConfirmText] = useState("");

  const load = useCallback(async () => {
    try { setM(await api<Mission>(`/missions/${id}`)); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Could not load mission"); }
  }, [id]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { api<{ items: LedgerEvent[] }>(`/missions/${id}/events`).then((r) => setEvents(r.items)).catch(() => undefined); }, [id]);
  useEffect(() => {
    const es = new EventSource(`/api/v1/missions/${id}/stream`);
    es.addEventListener("ledger", (ev) => {
      const e = JSON.parse((ev as MessageEvent).data) as LedgerEvent;
      setEvents((prev) => (prev.some((p) => p.seq === e.seq) ? prev : [...prev, e].sort((a, b) => a.seq - b.seq)));
      void load();
    });
    es.addEventListener("end", () => es.close());
    es.onerror = () => { /* browser reconnects; ledger is idempotent on seq */ };
    return () => es.close();
  }, [id, load]);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true); setError(null);
    try { await fn(); await load(); } catch (e) { setError(e instanceof ApiError ? e.message : "Action failed"); await load(); }
    finally { setBusy(false); }
  };

  const actions = m?.plan.actions ?? [];
  const pending = actions.filter((a) => a.status === "AWAITING_APPROVAL" && a.revision === m?.revision);
  const selected = useMemo(() => pending.filter((a) => picked[a.id] ?? true), [pending, picked]);

  if (!m) return error ? <ErrorNote error={error} /> : <p className="text-muted" role="status">Loading…</p>;
  const cl = m.clarification;
  const terminal = TERMINAL.includes(m.status) || (m.status === "CLASSIFIED" && cl?.type === "scam_warning");
  const stepIdx = STEPS.indexOf(m.status);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <header>
        <div className="flex flex-wrap items-center gap-2"><StatusBadge status={m.status} /><Tag>Revision {m.revision}</Tag>
          <Tag>Detected: {m.language_detected}</Tag><Tag>Selected: {m.language_selected}</Tag>{m.source === "voice" && <Tag tone="indigo">Voice transcript</Tag>}</div>
        <h1 className="mt-3 text-2xl font-extrabold tracking-tight sm:text-3xl">{m.intent}</h1>
        <p className="mt-1 text-sm text-muted">Domains: {m.domains.join(", ") || "none detected"} · Started {when(m.created_at, lang)}</p>
      </header>

      <ol className="flex gap-1 overflow-x-auto text-xs font-semibold" aria-label="Progress">
        {STEPS.map((s, i) => (<li key={s} className={`shrink-0 rounded-full px-3 py-1.5 ${i <= stepIdx ? "bg-teal-soft text-teal" : "bg-soft text-muted"}`} aria-current={s === m.status ? "step" : undefined}>{s.replaceAll("_", " ").toLowerCase()}</li>))}
      </ol>
      <ErrorNote error={error} />
      <ControlBar m={m} busy={busy} onAct={(fn) => void act(fn)} selectedIds={selected.map((a) => a.id)} />

      {cl && !terminal && (
        <section className="card border-amber" aria-labelledby="cl-h">
          <h2 id="cl-h" className="text-lg font-bold">{t("m.need")}</h2>
          <p className="mt-1 text-muted">{cl.message}</p>
          {cl.type === "low_confidence" && (<div className="mt-4 space-y-3">
            <label className="label" htmlFor="tr">Check what was heard</label>
            <textarea id="tr" defaultValue={cl.transcript} onChange={(e) => setCorrection(e.target.value)} className="input py-3" rows={2} />
            <button className="btn-primary" disabled={busy} onClick={() => act(() => api(`/missions/${id}/revise`, { body: correction.trim() ? { intent: correction.trim() } : { confirm_transcript: true } }))}>Confirm and continue</button></div>)}
          {cl.candidates && cl.candidates.length > 0 && (<ul className="mt-4 grid gap-2 sm:grid-cols-2">{cl.candidates.map((c) => (
            <li key={c.id}><button disabled={busy} className="btn-ghost h-full w-full flex-col items-start py-3 text-left" onClick={() => act(() => api(`/missions/${id}/bind`, { body: { role: cl.role, value: c.id } }))}>
              <span>{c.label}</span>{c.hint && <span className="text-xs font-normal text-muted">{c.hint}</span>}</button></li>))}</ul>)}
          {cl.type === "missing_field" && cl.role && (<div className="mt-4 flex gap-2"><input type="date" className="input max-w-xs" value={dateVal} onChange={(e) => setDateVal(e.target.value)} aria-label="Date" />
            <button className="btn-primary" disabled={!dateVal || busy} onClick={() => act(() => api(`/missions/${id}/bind`, { body: { role: cl.role, value: dateVal } }))}>Use this date</button></div>)}
          {(cl.type === "scam_warning" || cl.type === "refused") && <p className="mt-3 rounded-xl bg-danger-soft p-4 text-sm font-medium text-danger">{cl.message}</p>}
          {cl.type === "unsupported_or_unclear" && <p className="mt-3 text-sm text-muted">Supported today (against local fixtures): flight/hotel/calendar recovery, shop reservations, CRM follow-ups and complaint-case preparation. Rephrase below, or cancel.</p>}
        </section>
      )}

      {actions.length > 0 && (
        <section className="card" aria-labelledby="plan-h">
          <h2 id="plan-h" className="text-lg font-bold">{t("m.plan")}</h2>
          {m.plan.summary && <p className="mt-1 text-muted">{m.plan.summary}</p>}
          <ul className="mt-4 space-y-3">{actions.map((a) => <ActionRow key={a.id} a={a} lang={lang} stale={a.revision !== m.revision}
            checkable={m.status === "NEEDS_APPROVAL" && a.status === "AWAITING_APPROVAL"} checked={picked[a.id] ?? true} onCheck={(v) => setPicked((p) => ({ ...p, [a.id]: v }))} />)}</ul>
          {m.plan.blocked?.map((b) => (<div key={b.kind} className="mt-3 rounded-xl bg-soft p-4 text-sm"><Tag tone="amber">{b.reason}</Tag><p className="mt-2 text-muted">Voice call to the airline — {b.detail}</p></div>))}
          {m.plan.policy_citations?.map((c) => (<p key={c.id} className="mt-3 text-xs text-muted">Source: {c.title} · effective {c.effective_date} · {c.jurisdiction} {c.is_fixture && <Tag>fixture, not law</Tag>}</p>))}
          {m.plan.notes?.map((n) => <p key={n} className="mt-2 text-xs text-muted">• {n}</p>)}
          <div className="mt-5 flex flex-wrap gap-3">
            {m.status === "NEEDS_APPROVAL" && <button className="btn-primary" disabled={busy || selected.length === 0}
              onClick={() => act(() => api(`/missions/${id}/approve`, { body: { approvals: selected.map((a) => ({ action_id: a.id, digest: a.digest })) } }))}>{t("m.approve")} {selected.length} action{selected.length === 1 ? "" : "s"}</button>}
            {m.status === "AUTHORIZED" && <button className="btn-teal" disabled={busy} onClick={() => act(() => api(`/missions/${id}/execute`, { method: "POST" }))}>{t("m.run")}</button>}
            {m.status === "UNCERTAIN" && <button className="btn-primary" disabled={busy} onClick={() => act(() => api(`/missions/${id}/reconcile`, { method: "POST" }))}>{t("m.recheck")}</button>}
            {!terminal && <button className="btn-ghost" disabled={busy} onClick={() => act(() => api(`/missions/${id}/cancel`, { method: "POST" }))}>{t("m.cancel")}</button>}
          </div>
        </section>
      )}

      {!terminal && (
        <section className="card" aria-labelledby="fix-h">
          <h2 id="fix-h" className="text-lg font-bold">{t("m.change")}</h2>
          <p className="mt-1 text-sm text-muted">A correction replaces the instruction and cancels any approval you already gave.</p>
          <div className="mt-3 flex flex-col gap-2 sm:flex-row"><label htmlFor="fix" className="sr-only">Corrected request</label>
            <input id="fix" className="input" value={confirmText} onChange={(e) => setConfirmText(e.target.value)} placeholder="e.g. Flight FA2087 cancelled, I need the refund" />
            <button className="btn-ghost shrink-0" disabled={busy || confirmText.trim().length < 3} onClick={() => act(async () => { await api(`/missions/${id}/revise`, { body: { intent: confirmText.trim() } }); setConfirmText(""); })}>{t("m.replace")}</button></div>
        </section>
      )}

      <Alternatives m={m} lang={lang} />

      {m.outcome && <Receipt m={m} />}

      <EvidenceCenter missionId={id} refreshKey={`${m.status}-${m.revision}-${events.length}`} />
      <AgentActivity missionId={id} refreshKey={`${m.status}-${events.length}`} />

      {!terminal && (m.scenario === "flight_recovery" || m.scenario === "retail_reservation") && actions.length > 0 && (
        <section className="rounded-2xl border border-dashed border-line p-5" aria-labelledby="fault-h">
          <h2 id="fault-h" className="font-bold">Demo controls <Tag tone="amber">fixture fault injection</Tag></h2>
          <p className="mt-1 text-sm text-muted">Arms a one-time failure inside the <em>local fixture provider</em> so you can watch recovery. It never touches a real service.</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button className="btn-ghost" disabled={busy} onClick={() => act(() => api(`/missions/${id}/faults`, { body: { kind: "ack_loss" } }))}>Lose the provider’s acknowledgement</button>
            <button className="btn-ghost" disabled={busy} onClick={() => act(() => api(`/missions/${id}/faults`, { body: { kind: "silent_drop" } }))}>Provider says OK but drops it</button></div>
        </section>
      )}

      <section aria-labelledby="led-h"><h2 id="led-h" className="mb-3 text-lg font-bold">{t("m.ledger")}</h2>
        {events.length === 0 ? <Empty title="No events yet" /> : (
          <ol className="space-y-1 rounded-2xl border border-line bg-surface p-3 text-sm">{events.map((e) => (
            <li key={e.seq} className="flex gap-3 rounded-lg px-2 py-1.5 hover:bg-soft"><span className="w-8 shrink-0 text-right text-xs text-muted">{e.seq}</span>
              <span className={`w-48 shrink-0 font-semibold ${/FAIL|ABORT|STALE|LOST|INVALID|REVOKED/.test(e.type) ? "text-danger" : e.type.startsWith("VERIFIED") ? "text-teal" : ""}`}>{e.type}</span>
              <span className="min-w-0 truncate text-muted">{summarise(e)}</span></li>))}</ol>)}
      </section>
    </div>
  );
}

function summarise(e: LedgerEvent): string {
  const d = e.data;
  if (e.type === "STATE") return `${d.from} → ${d.to}`;
  if (e.type === "CLASSIFIED") return `${(d.domains as string[]).join(", ")} (${d.language_detected})`;
  return Object.entries(d).filter(([, v]) => typeof v !== "object").map(([k, v]) => `${k}=${String(v)}`).join(" ").slice(0, 120);
}

function ActionRow({ a, lang, stale, checkable, checked, onCheck }: { a: PlanAction; lang: string; stale: boolean; checkable: boolean; checked: boolean; onCheck: (v: boolean) => void }) {
  const p = a.params as Record<string, string | number>;
  const target = p.contact_name ? `To ${p.contact_name}: “${String(p.body).slice(0, 80)}…”` : p.lead_name ? `${p.lead_name} (phone ending ${p.phone_last4}) → ${p.follow_up_date}` : p.event_id ? String(p.title) : p.domain ? String(p.title) : p.booking_ref ? `${p.booking_ref}${p.passenger_name ? ` · ${p.passenger_name}` : ""}` : `${p.product_name} → ${p.customer_name}, pickup ${p.pickup_date}`;
  return (
    <li className={`rounded-xl border border-line p-4 ${stale ? "opacity-50" : ""}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          {checkable && <input type="checkbox" className="mt-1.5 h-5 w-5" checked={checked} onChange={(e) => onCheck(e.target.checked)} aria-label={`Include ${KIND_LABEL[a.kind] ?? a.kind}`} />}
          <div><p className="font-semibold">{KIND_LABEL[a.kind] ?? a.kind}</p><p className="text-sm text-muted">{target}</p></div></div>
        <div className="text-right"><p className="font-bold">{a.amount_paise == null ? "No charge" : inr(a.amount_paise, lang)}</p><StatusBadge status={a.status === "AWAITING_APPROVAL" ? "NEEDS_APPROVAL" : a.status} /></div>
      </div>
      {a.depends_on && a.depends_on.length > 0 && <p className="mt-1 text-xs text-muted">Runs only after: {a.depends_on.length} earlier action verified</p>}
      <p className="mt-2 text-xs text-muted">Approval is bound to digest <code>{a.digest.slice(0, 12)}…</code> · risk: {a.risk.replaceAll("_", " ")}</p>
    </li>
  );
}

function Receipt({ m }: { m: Mission }) {
  const { t } = useI18n();
  const o = m.outcome!;
  const download = () => {
    const blob = new Blob([JSON.stringify({ mission_id: m.id, intent: m.intent, outcome: o }, null, 2)], { type: "application/json" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `redeem-receipt-${m.id}.json`; a.click(); URL.revokeObjectURL(a.href);
  };
  return (
    <section className="card" aria-labelledby="rc-h">
      <div className="flex flex-wrap items-center justify-between gap-3"><h2 id="rc-h" className="text-lg font-bold">{t("m.receipt")} — {o.headline}</h2><button className="btn-ghost" onClick={download}>{t("m.download")}</button></div>
      {o.reason === "out_of_stock" && <p className="mt-2 text-muted">That item is out of stock. In stock instead: {o.alternatives?.map((x) => `${x.name} (${x.stock})`).join(", ") || "nothing similar"}.</p>}
      {o.summary && <p className="mt-2 text-muted">{o.summary}</p>}
      {o.claims?.map((c) => (<div key={c.action_id} className="mt-3 rounded-xl bg-soft p-4 text-sm"><Tag tone={c.result === "VERIFIED" ? "teal" : "danger"}>{c.result}</Tag>
        <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-words text-xs text-muted">{JSON.stringify(c.evidence, null, 2)}</pre></div>))}
      {o.outstanding && o.outstanding.length > 0 && (<div className="mt-4"><h3 className="font-semibold">Still outstanding</h3><ul className="mt-1 list-disc pl-5 text-sm text-muted">{o.outstanding.map((x, i) => <li key={i}>{x.kind.replaceAll("_", " ")} — {x.reason}</li>)}</ul></div>)}
      {o.scope && <p className="mt-4 text-xs text-muted">{o.scope.note}</p>}
      {o.ledger_chain_head && <p className="mt-1 break-all text-xs text-muted">Ledger hash ({o.ledger_events} events): {o.ledger_chain_head}</p>}
    </section>
  );
}
