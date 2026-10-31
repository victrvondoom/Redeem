"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ErrorNote, PageTitle, Tag } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

type Item = { id: string; category: string; field: string; label: string; value: string; source_kind: string; source_ref: string | null; segment: string | null; explicit: boolean; confidence: number;
  status: "proposed" | "confirmed" | "rejected"; pinned: boolean; quote: string | null; simulated: boolean; expires_at: string | null; updated_at: string };
type Field = { field: string; category: string; label: string; sensitive: boolean; question: string; options: string[] };
type Turn = { id: string; channel: string; role: string; text: string; at: string; ref_id: string | null };
type Resp = { items: Item[]; capture_consent: boolean; fields: Field[] };
type Ingest = { saved: Item[]; ambiguous: boolean; clarification: string | null; unmapped: boolean; needs_confirmation: string[] };

const SRC: Record<string, string> = { bolna_call: "Bolna call", bolna_fixture: "Simulated Bolna answer", typed: "Typed by you", mission: "Mission" };

export default function MemoryCenter() {
  const [data, setData] = useState<Resp | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const [utt, setUtt] = useState("");
  const [field, setField] = useState("");
  const [sim, setSim] = useState(true);
  const [note, setNote] = useState<string | null>(null);
  const [edit, setEdit] = useState<{ id: string; v: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [turns, setTurns] = useState<Turn[] | null>(null);

  const load = useCallback(async () => {
    try { const p = new URLSearchParams(); if (q) p.set("q", q); if (cat) p.set("category", cat); setData(await api<Resp>(`/memory?${p}`)); setTurns((await api<{ turns: Turn[] }>("/context?limit=40")).turns); setError(null); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Could not load memory"); }
  }, [q, cat]);
  useEffect(() => { const t = setTimeout(() => void load(), 200); return () => clearTimeout(t); }, [load]);

  const act = async (fn: () => Promise<unknown>) => { setBusy(true); setError(null); try { await fn(); await load(); } catch (e) { setError(e instanceof ApiError ? e.message : "Action failed"); } finally { setBusy(false); } };
  const teach = () => act(async () => {
    const r = await api<Ingest>("/memory/ingest", { method: "POST", body: { utterance: utt, expected_field: field || null, fixture: sim } });
    setNote(r.ambiguous || r.unmapped ? `Ask the caller: ${r.clarification ?? "Could you say that again?"}` : `Saved ${r.saved.length} item(s)${r.needs_confirmation.length ? " — sensitive or uncertain, confirm below" : ""}.`);
    if (!r.ambiguous && !r.unmapped) setUtt("");
  });
  const download = () => act(async () => {
    const j = await api<{ memory: Item[] }>("/privacy/export");
    const url = URL.createObjectURL(new Blob([JSON.stringify(j.memory, null, 2)], { type: "application/json" }));
    const a = document.createElement("a"); a.href = url; a.download = "redeem-memory.json"; a.click(); URL.revokeObjectURL(url);
  });
  const cats = useMemo(() => [...new Set((data?.fields ?? []).map((f) => f.category))], [data]);
  const question = data?.fields.find((f) => f.field === field)?.question;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageTitle title="Memory Center" sub="What REDEEM remembers about you, where each fact came from, and whether you confirmed it. Only confirmed memory is used in missions. Values are encrypted at rest." />
      <ErrorNote error={error} />
      <section className="card" aria-labelledby="cap-h">
        <div className="flex flex-wrap items-center justify-between gap-3"><h2 id="cap-h" className="text-lg font-bold">Capture from voice</h2>
          <label className="flex min-h-[44px] items-center gap-2 text-sm font-semibold"><input type="checkbox" className="h-5 w-5 accent-[rgb(255,122,26)]" checked={!!data?.capture_consent} disabled={busy || !data}
            onChange={(e) => void act(() => api(`/memory/consent?granted=${e.target.checked}`, { method: "POST" }))} />Let REDEEM save answers from my Bolna calls</label></div>
        <p className="mt-1 text-sm text-muted">With consent, the caller&apos;s own lines from a Bolna call are mapped to fields. Without live Bolna credentials you can try the same mapper below; those answers are labelled <em>simulated</em>.</p>
        <div className="mt-4 grid gap-3 md:grid-cols-[1fr_1.4fr]">
          <div><label className="label" htmlFor="m-field">Question that was asked</label>
            <select id="m-field" className="input" value={field} onChange={(e) => setField(e.target.value)}><option value="">Free speech (detect fields)</option>{data?.fields.map((f) => <option key={f.field} value={f.field}>{f.label}</option>)}</select>
            {question && <p className="mt-1 text-xs text-muted">“{question}”</p>}</div>
          <div><label className="label" htmlFor="m-utt">The answer (spoken or typed)</label>
            <input id="m-utt" className="input" value={utt} onChange={(e) => setUtt(e.target.value)} placeholder="e.g. window seat, vegetarian, WhatsApp please" /></div>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3"><button className="btn-primary" disabled={busy || !utt.trim()} onClick={() => void teach()}>Map and save</button>
          <label className="flex items-center gap-2 text-sm text-muted"><input type="checkbox" className="h-4 w-4 accent-[rgb(255,122,26)]" checked={sim} onChange={(e) => setSim(e.target.checked)} />Label as simulated Bolna answer</label></div>
        {note && <p role="status" className="mt-3 rounded-xl bg-soft p-3 text-sm">{note}</p>}
      </section>

      <section aria-labelledby="mem-h" className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3"><h2 id="mem-h" className="text-lg font-bold">Saved memory</h2>
          <div className="flex flex-wrap items-center gap-2"><input className="input !w-48" aria-label="Search memory" placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} />
            <select className="input !w-40" aria-label="Category" value={cat} onChange={(e) => setCat(e.target.value)}><option value="">All categories</option>{cats.map((c) => <option key={c}>{c}</option>)}</select>
            <button className="btn-ghost" onClick={() => void download()}>Export</button></div></div>
        {data && data.items.length === 0 && <div className="card text-center text-muted">Nothing saved yet. Teach REDEEM a preference above, or consent and make a Bolna call.</div>}
        <ul className="space-y-3">{data?.items.map((m) => (
          <li key={m.id} className="card !p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0"><p className="text-xs font-bold text-muted">{m.label}</p>
                {edit?.id === m.id ? (<div className="mt-1 flex gap-2"><input className="input" aria-label="Corrected value" value={edit.v} onChange={(e) => setEdit({ id: m.id, v: e.target.value })} /><button className="btn-primary" disabled={busy} onClick={() => void act(async () => { await api(`/memory/${m.id}/confirm`, { method: "POST", body: { value: edit.v } }); setEdit(null); })}>Save</button></div>)
                  : <p className="mt-0.5 text-xl font-bold">{m.value}</p>}
                <p className="mt-1 text-sm text-muted">{m.quote && <>“{m.quote}”, </>}{SRC[m.source_kind] ?? m.source_kind}{m.source_ref ? ` ${m.source_ref}` : ""}{m.segment ? `, line ${m.segment}` : ""}, {m.explicit ? "explicit" : "inferred"}, confidence {Math.round(m.confidence * 100)}%{m.expires_at ? `, expires ${m.expires_at.slice(0, 10)}` : ""}</p></div>
              <div className="flex flex-wrap items-center gap-2">{m.simulated && <Tag tone="amber">simulated</Tag>}{m.pinned && <Tag tone="indigo">pinned</Tag>}
                <Tag tone={m.status === "confirmed" ? "teal" : m.status === "rejected" ? "danger" : "amber"}>{m.status === "proposed" ? "needs your confirmation" : m.status}</Tag></div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {m.status !== "confirmed" && <button className="btn-teal !min-h-[40px]" disabled={busy} onClick={() => void act(() => api(`/memory/${m.id}/confirm`, { method: "POST" }))}>Confirm</button>}
              {m.status !== "rejected" && <button className="btn-ghost !min-h-[40px]" disabled={busy} onClick={() => void act(() => api(`/memory/${m.id}/reject`, { method: "POST" }))}>Reject</button>}
              <button className="btn-ghost !min-h-[40px]" onClick={() => setEdit({ id: m.id, v: m.value })}>Correct</button>
              <button className="btn-ghost !min-h-[40px]" disabled={busy} onClick={() => void act(() => api(`/memory/${m.id}`, { method: "PATCH", body: { pinned: !m.pinned } }))}>{m.pinned ? "Unpin" : "Pin"}</button>
              <button className="btn-ghost !min-h-[40px] text-danger" disabled={busy} onClick={() => void act(() => api(`/memory/${m.id}`, { method: "DELETE" }))}>Delete</button>
            </div></li>))}</ul>
        {data && data.items.length > 0 && cat && <button className="btn-ghost text-danger" disabled={busy} onClick={() => { if (confirm(`Delete every saved ${cat} item?`)) void act(() => api(`/memory?category=${cat}`, { method: "DELETE" })); }}>Delete all “{cat}” memory</button>}
      </section>
      <section className="card" aria-labelledby="ctx-h">
        <div className="flex flex-wrap items-center justify-between gap-3"><h2 id="ctx-h" className="text-lg font-bold">Conversation context</h2>
          <button className="btn-ghost text-danger" disabled={busy || !turns?.length} onClick={() => { if (confirm("Forget your saved conversation context?")) void act(() => api("/context", { method: "DELETE" })); }}>Forget context</button></div>
        <p className="mt-1 text-sm text-muted">What you and REDEEM said, per mission or call, kept so short follow-ups (“also move my hotel”) keep their context. Encrypted at rest; only you can see it.</p>
        {turns && turns.length === 0 && <p className="mt-3 text-sm text-muted">Nothing yet. Start a mission and it appears here.</p>}
        <ol className="mt-3 max-h-80 space-y-1.5 overflow-y-auto" aria-label="Conversation turns">{turns?.map((t) => (<li key={t.id} className={`rounded-xl px-3 py-2 text-sm ${t.role === "user" ? "bg-soft" : "border border-line"}`}><span className="mr-2 text-xs font-bold text-teal">{t.role === "user" ? "You" : "REDEEM"}, {t.channel}</span>{t.text}</li>))}</ol>
      </section>
    </div>
  );
}
