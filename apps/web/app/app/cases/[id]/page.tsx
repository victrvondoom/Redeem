"use client";
import { use, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Icon } from "@/components/Icons";
import { Empty, ErrorNote, Tag } from "@/components/ui";
import { Meter, Stepper, Tabs } from "@/components/viz";
import { api, ApiError } from "@/lib/api";
import { inr, when } from "@/lib/format";
import type { CaseView, Source } from "@/lib/types";

const FACT_TONE: Record<string, "teal" | "danger" | "amber"> = { SUPPORTED: "teal", CONTRADICTED: "danger", UNSUPPORTED: "amber" };
const W_KEYS = ["benefit", "cost", "delay", "risk", "privacy"] as const;

export default function CaseWorkspace({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [c, setC] = useState<CaseView | null>(null);
  const [tab, setTab] = useState("overview");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [intake, setIntake] = useState<Record<string, string>>({});
  const [draft, setDraft] = useState("");
  const [draftDirty, setDraftDirty] = useState(false);
  const [weights, setWeights] = useState<Record<string, number>>({ benefit: 0.35, cost: 0.2, delay: 0.2, risk: 0.15, privacy: 0.1 });
  const [actionKey, setActionKey] = useState("");
  const [track, setTrack] = useState({ kind: "acknowledgement", reference: "", note: "", amount_inr: "", document_id: "" });
  const [vault, setVault] = useState<{ id: string; filename: string }[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  const apply = useCallback((v: CaseView) => { setC(v); setIntake((p) => ({ ...v.intake, ...(Object.keys(p).length && p._dirty ? p : {}) })); if (v.draft && !draftDirty) setDraft(v.draft.body); setActionKey((k) => k || v.draft?.approval_action || ""); }, [draftDirty]);
  const load = useCallback(async () => { try { apply(await api<CaseView>(`/cases/${id}`)); } catch (e) { setError(e instanceof ApiError ? e.message : "Could not load the case"); } }, [id, apply]);
  useEffect(() => { void load(); api<{ items: { id: string; filename: string }[] }>("/documents?limit=100").then((r) => setVault(r.items)).catch(() => undefined); }, [load]);

  const act = async (fn: () => Promise<unknown>, ok?: string) => {
    setBusy(true); setError(null); setNotice(null);
    try { const r = await fn(); if (r && typeof r === "object" && "id" in (r as object) && (r as CaseView).stages) apply(r as CaseView); else await load(); if (ok) setNotice(ok); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Action failed"); await load(); } finally { setBusy(false); }
  };
  const upload = async (file: File) => {
    const form = new FormData(); form.append("file", file);
    await act(async () => { const r = await api<{ ingest: { duplicate?: boolean; note?: string; near_duplicate_of?: string }; case: CaseView; doc_type: string; relevance: { relevant: boolean; reason: string } }>(`/cases/${id}/documents`, { form });
      setNotice(r.ingest.duplicate ? (r.ingest.note ?? "Duplicate") : `${file.name}: classified as ${r.doc_type?.replaceAll("_", " ")}. ${r.relevance.relevant ? "" : "Not relevant: " + r.relevance.reason}${r.ingest.near_duplicate_of ? " Near-duplicate of an existing file." : ""}`); return r.case; });
  };

  if (!c) return error ? <ErrorNote error={error} /> : <p className="text-muted" role="status">Loading…</p>;
  const reached = Array.from(new Set(c.events.filter((e) => e.type === "STAGE").map((e) => String(e.data.stage))));
  const locked = ["SUBMITTED", "TRACKING", "RESOLVED", "UNRESOLVED", "CLOSED"].includes(c.status);
  const cov = c.checklist.filter((x) => x.covered).length;
  const next = c.status === "AWAITING_INFO" ? "Answer the questions below so the analysis can finish." : c.status === "AWAITING_APPROVAL" ? "Review the draft, then approve it." : c.status === "APPROVED" ? "Submit: records it and shows where to file." :
    c.status === "SUBMITTED" ? "File it with the authority, then log the acknowledgement." : c.status === "TRACKING" ? "Log responses; mark the outcome when it is resolved or refused." : c.status === "RESOLVED" || c.status === "UNRESOLVED" ? "Download the report or close the case." : "Review the analysis.";
  const dl = async (path: string, name: string, mime: string) => { const r = await fetch(`/api/v1${path}`, { credentials: "same-origin" }); const b = new Blob([await r.arrayBuffer()], { type: mime }); const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = name; a.click(); URL.revokeObjectURL(a.href); };

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <header>
        <div className="flex flex-wrap items-center gap-2"><Tag tone="indigo">{c.domain_label}</Tag><Tag tone={c.status === "RESOLVED" ? "teal" : c.status === "UNRESOLVED" ? "danger" : "amber"}>{c.status.replaceAll("_", " ").toLowerCase()}</Tag>
          {c.overdue && <Tag tone="danger">follow-up overdue</Tag>}{c.mission_id && <a href={`/app/missions/${c.mission_id}`} className="badge bg-soft text-indigo">from mission</a>}</div>
        <h1 className="mt-2 text-2xl font-normal tracking-tight sm:text-3xl">{c.title}</h1>
        <p className="mt-1 text-sm text-muted">{c.provider ?? "provider not identified"}, {c.claimed_paise ? `${inr(c.claimed_paise)} at stake, ` : ""}incident {c.incident_date ?? "date unknown"}, follow-up by {c.followup_date ?? "—"}, case <code>{c.id}</code></p>
      </header>
      <Stepper stages={c.stages} current={c.stage} reached={reached} />
      <ErrorNote error={error} />
      {notice && <p role="status" className="rounded-xl bg-teal-soft px-4 py-3 text-sm font-medium text-teal">{notice}</p>}
      <div className="rounded-xl bg-indigo-soft px-4 py-3 text-sm"><strong className="text-indigo">Next:</strong> {next}</div>

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="min-w-0 space-y-5">
          <Tabs value={tab} onChange={setTab} tabs={[{ id: "overview", label: "Overview" }, { id: "evidence", label: "Evidence", count: c.documents.length }, { id: "sources", label: "Sources", count: c.sources.length }, { id: "options", label: "Options", count: c.ranking.ranked?.length }, { id: "draft", label: "Draft & approval" }, { id: "track", label: "Submit & track" }]} />

          {tab === "overview" && (<>
            {c.missing.length > 0 && (
              <section className="card border-indigo" aria-labelledby="mi-h"><h2 id="mi-h" className="text-lg font-bold">I need a few facts</h2><p className="text-sm text-muted">Only what is genuinely missing for this domain.</p>
                <div className="mt-3 space-y-3">{c.missing.map((m) => (<div key={m.field}><label className="label" htmlFor={`m-${m.field}`}>{m.question}</label>
                  <input id={`m-${m.field}`} className="input" placeholder={m.example ? `e.g. ${m.example.replace(/^e\.g\. /, "")}` : ""} value={intake[m.field] ?? ""} onChange={(e) => setIntake({ ...intake, [m.field]: e.target.value, _dirty: "1" })} /></div>))}</div>
                <button className="btn-primary mt-4" disabled={busy} onClick={() => void act(() => api(`/cases/${id}/intake`, { method: "PATCH", body: { fields: Object.fromEntries(c.missing.map((m) => [m.field, intake[m.field] ?? ""]).filter(([, v]) => v)) } }), "Saved and re-analysed.")}>Save and continue</button></section>)}
            <section className="card" aria-labelledby="an-h"><h2 id="an-h" className="text-lg font-bold">Analysis</h2>
              <p className="mt-2 text-sm">{c.analysis.summary}</p>
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <div><p className="text-xs font-bold text-muted">Confidence</p><div className="mt-1"><Meter value={c.analysis.confidence} tone="indigo" label="Analysis confidence" /></div><p className="mt-1 text-xs text-muted">{c.analysis.confidence_explanation}</p></div>
                <div><p className="text-xs font-bold text-muted">Evidence checklist</p><div className="mt-1"><Meter value={cov} max={c.checklist.length} label="Checklist coverage" /></div><p className="mt-1 text-xs text-muted">{cov} of {c.checklist.length} items covered</p></div></div>
              <div className="mt-5 grid gap-5 sm:grid-cols-2">
                <div><h3 className="text-sm font-bold">Established by documents</h3>{c.analysis.established_facts.length ? <ul className="mt-2 space-y-1.5 text-sm">{c.analysis.established_facts.map((f, i) => <li key={i} className="flex gap-2"><span className="text-teal"><Icon name="check" size={14} /></span><span>{f.claim}<span className="block text-xs text-muted">{f.support[0]?.filename}{f.support[0]?.quote ? ` — “…${f.support[0].quote}…”` : ""}</span></span></li>)}</ul> : <p className="mt-2 text-sm text-muted">Nothing yet. Attach documents to support your claims.</p>}</div>
                <div><h3 className="text-sm font-bold">Stated but not yet supported</h3>{c.analysis.uncertain_claims.length ? <ul className="mt-2 space-y-1.5 text-sm">{c.analysis.uncertain_claims.map((f, i) => <li key={i} className="flex gap-2"><Tag tone={FACT_TONE[f.status] ?? "amber"}>{f.status.toLowerCase()}</Tag><span>{f.claim}{f.support[0]?.note && <span className="block text-xs text-danger">{f.support[0].note}</span>}</span></li>)}</ul> : <p className="mt-2 text-sm text-muted">None.</p>}</div></div>
              {c.analysis.risks.length > 0 && <div className="mt-4 rounded-xl bg-amber-soft p-4 text-sm"><p className="font-semibold">Risks and gaps</p><ul className="mt-1 list-disc pl-5">{c.analysis.risks.map((r) => <li key={r}>{r}</li>)}</ul></div>}
              {c.analysis.healthcare_note && <p className="mt-3 rounded-xl bg-soft p-3 text-sm">{c.analysis.healthcare_note}</p>}
            </section>
            <section className="card" aria-labelledby="it-h"><h2 id="it-h" className="text-lg font-bold">Case facts</h2><p className="text-sm text-muted">Extracted from your text and documents. Edit anything; the analysis re-runs and any approval is voided.</p>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">{Object.entries(c.schema).filter(([k]) => k !== "reason_for_rejection" || true).map(([k, ex]) => (<div key={k}><label className="label" htmlFor={`f-${k}`}>{k.replaceAll("_", " ")}{c.critical.includes(k) && <span className="ml-1 text-xs text-danger">required</span>}</label>
                <input id={`f-${k}`} className="input" disabled={locked} value={intake[k] ?? c.intake[k] ?? ""} placeholder={ex} onChange={(e) => setIntake({ ...intake, [k]: e.target.value, _dirty: "1" })} /></div>))}</div>
              {!locked && <button className="btn-ghost mt-4" disabled={busy} onClick={() => void act(() => api(`/cases/${id}/intake`, { method: "PATCH", body: { fields: Object.fromEntries(Object.entries(intake).filter(([k, v]) => k !== "_dirty" && v && v !== c.intake[k])) } }), "Facts updated; analysis re-run.")}>Save facts</button>}
            </section>
            <section className="card" aria-labelledby="es-h"><h2 id="es-h" className="text-lg font-bold">Where to escalate</h2><p className="text-sm text-muted">From RECLAIM&apos;s domain profile; contact details are not independently verified — check them on the official site.</p>
              <ol className="mt-3 space-y-3">{c.analysis.remedies.map((r) => (<li key={r.order} className="flex gap-3"><span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-indigo-soft text-sm font-bold text-indigo">{r.order}</span>
                <div className="text-sm"><Tag>{r.stage}</Tag><p className="mt-1">{r.text}</p>{r.links.map((l) => <a key={l} href={l} target="_blank" rel="noopener noreferrer" className="mr-3 text-xs font-semibold text-indigo underline">{l.replace(/^https?:\/\//, "")}</a>)}</div></li>))}</ol></section>
            {c.analysis.timeline.length > 0 && <section className="card"><h2 className="text-lg font-bold">Timeline of events</h2><ol className="mt-3 space-y-2 border-l-2 border-line pl-4 text-sm">{c.analysis.timeline.map((t, i) => <li key={i}><span className="font-semibold">{t.date ?? "—"}</span> — {t.event}</li>)}</ol></section>}
          </>)}

          {tab === "evidence" && (<>
            <section className="card" aria-labelledby="ck-h"><div className="flex flex-wrap items-center justify-between gap-2"><h2 id="ck-h" className="text-lg font-bold">Evidence checklist</h2>
              <div><input ref={fileRef} type="file" className="sr-only" aria-label="Upload evidence" accept=".txt,.md,.csv,.pdf,.png,.jpg,.jpeg" onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); e.target.value = ""; }} />
                <button className="btn-primary" disabled={busy || locked} onClick={() => fileRef.current?.click()}>Upload evidence</button></div></div>
              <ul className="mt-3 divide-y divide-line">{c.checklist.map((x) => (<li key={x.id} className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm"><span className="flex items-center gap-2"><span className={x.covered ? "text-teal" : "text-muted"}><Icon name={x.covered ? "check" : "alert"} size={16} /></span>{x.label}</span>
                <span className="text-xs text-muted">{x.document ? `${x.document.filename}, strength ${Math.round(x.strength * 100)}%` : "missing"}</span></li>))}</ul>
              <div className="mt-3 flex flex-wrap items-center gap-2"><label htmlFor="link" className="text-sm font-semibold">Use a file already in your vault:</label>
                <select id="link" className="input !min-h-[40px] max-w-xs" defaultValue="" onChange={(e) => { const v = e.target.value; e.target.value = ""; if (v) { const f = new FormData(); f.append("document_id", v); void act(async () => (await api<{ case: CaseView }>(`/cases/${id}/documents`, { form: f })).case, "Linked from your vault."); } }}>
                  <option value="">Choose…</option>{vault.map((d) => <option key={d.id} value={d.id}>{d.filename}</option>)}</select></div></section>
            {c.documents.length === 0 ? <Empty title="No documents attached">Upload a ticket, bill, rejection letter or screenshot. Text and PDF are read; images are stored but OCR is unavailable here.</Empty> : c.documents.map((d) => (
              <section key={d.id} className="card" aria-label={d.filename}><div className="flex flex-wrap items-start justify-between gap-2"><div><h3 className="font-bold">{d.filename} <Tag>v{d.version}</Tag> <Tag tone="indigo">{d.doc_type?.replaceAll("_", " ") ?? "other"}</Tag></h3>
                <p className="text-xs text-muted">sha256 {d.sha256.slice(0, 14)}… {d.page_count ? `· ${d.page_count} page(s)` : ""} {d.ocr_status && <span className="text-danger">· {d.ocr_status.replaceAll("_", " ")}</span>}</p></div>
                <button className="btn-ghost" disabled={busy || locked} onClick={() => void act(() => api(`/cases/${id}/documents/${d.id}`, { method: "DELETE" }), "Detached from the case.")}>Detach</button></div>
                <div className="mt-3 grid gap-3 sm:grid-cols-2"><div><p className="text-xs font-semibold text-muted">Evidence strength</p><Meter value={d.strength.score} tone={d.strength.score >= 0.35 ? "teal" : "amber"} label="Strength" /><p className="mt-1 text-xs text-muted">{d.strength.explanation}</p></div>
                  <div><p className="text-xs font-semibold text-muted">Relevance</p><p className="text-sm">{d.relevance.relevant ? <span className="text-teal">Relevant</span> : <span className="text-danger">Not relevant</span>} — {d.relevance.reason}</p>{d.near_duplicate_of && <p className="text-xs text-amber">Near-duplicate of another file.</p>}</div></div>
                {d.facts.length > 0 && <div className="mt-3"><p className="text-xs font-semibold text-muted">Extracted facts (with source)</p><ul className="mt-1 space-y-1 text-sm">{d.facts.filter((f) => f.kind !== "provider").slice(0, 10).map((f, i) => (<li key={i} className="flex flex-wrap gap-2"><Tag>{f.kind.replaceAll("_", " ")}</Tag><strong>{f.display}</strong>{f.quote && <span className="text-xs text-muted">p.{f.page ?? 1}: “…<mark className="bg-amber-soft px-0.5">{f.display}</mark>…” — {f.quote}</span>}</li>))}</ul></div>}
              </section>))}
            <section className="card" aria-labelledby="cm-h"><h2 id="cm-h" className="text-lg font-bold">Evidence-to-claim mapping</h2><p className="text-sm text-muted">Each fact you stated is checked against your documents.</p>
              {c.claims.length === 0 ? <p className="mt-2 text-sm text-muted">No claims yet.</p> : <ul className="mt-3 space-y-2">{c.claims.map((m) => (<li key={m.field} className="rounded-xl border border-line p-3 text-sm"><div className="flex flex-wrap items-center gap-2"><Tag tone={FACT_TONE[m.status] ?? "amber"}>{m.status.toLowerCase()}</Tag><strong>{m.claim}</strong></div>
                {m.support.map((s, i) => <p key={i} className="mt-1 text-xs text-muted">{s.filename}{s.quote ? ` — “…${s.quote}…”` : ""}{s.note ? ` — ${s.note}` : ""}</p>)}{m.status === "UNSUPPORTED" && <p className="mt-1 text-xs text-muted">Only you have stated this so far. REDEEM will not treat it as established.</p>}</li>))}</ul>}</section>
          </>)}

          {tab === "sources" && (<section className="space-y-4" aria-label="Sources">
            <p className="rounded-xl bg-soft p-4 text-sm">{c.analysis.basis_note}</p>
            {c.sources.length === 0 ? <Empty title="No sources retrieved">No knowledge was inherited for this domain, so REDEEM cites nothing and asserts no legal basis.</Empty> : c.sources.map((s: Source) => (
              <article key={s.id} className="card"><div className="flex flex-wrap items-center gap-2"><Tag tone={s.provenance === "scraped_official" ? "teal" : "amber"}>{s.provenance === "scraped_official" ? "scraped from an official page" : "authored guide (not an official text)"}</Tag><Tag>{s.authority || "unknown authority"}</Tag><code className="text-xs">{s.id}</code></div>
                <h3 className="mt-2 font-bold">{s.title}</h3>{s.source_url && <a href={s.source_url} target="_blank" rel="noopener noreferrer" className="break-all text-xs font-semibold text-indigo underline">{s.source_url}</a>}
                <p className="mt-2 whitespace-pre-wrap text-sm text-muted">{s.passage}…</p>
                <div className="mt-3 grid gap-2 sm:grid-cols-2">{(["similarity", "authority", "legal_weight", "confidence"] as const).map((k) => <div key={k}><p className="text-xs text-muted">{k.replace("_", " ")}</p><Meter value={s.evidence_scores[k]} tone={k === "confidence" ? "indigo" : "teal"} label={k} /></div>)}</div></article>))}
          </section>)}

          {tab === "options" && (<>
            <section className="card" aria-labelledby="op-h"><h2 id="op-h" className="text-lg font-bold">Ranked options</h2><p className="text-sm text-muted">{c.ranking.model?.formula}. {c.assumption_note}</p>
              <ol className="mt-4 space-y-3">{c.ranking.ranked.map((r, i) => (<li key={r.key} className={`rounded-xl border p-4 ${r.eligible ? "border-line" : "border-line opacity-70"}`}><div className="flex flex-wrap items-center justify-between gap-2"><p className="font-bold">{i + 1}. {r.name}</p>
                <div className="flex gap-2"><Tag tone={r.eligible ? "teal" : "danger"}>{r.eligible ? "eligible" : "blocked"}</Tag><Tag>{r.stage}</Tag><Tag tone="indigo">utility {r.utility.toFixed(2)}</Tag></div></div>
                <p className="mt-1 text-sm text-muted">{r.rationale}</p><div className="mt-2 grid gap-2 sm:grid-cols-3 text-xs"><span>Est. time ~{r.delay_days} days</span><span>Risk {Math.round(r.risk * 100)}%</span><span>Privacy exposure {Math.round(r.privacy * 100)}%</span></div>
                <p className="mt-1 text-xs text-muted">Assumption: {r.assumptions[0]}</p></li>))}</ol></section>
            <section className="card" aria-labelledby="wt-h"><h2 id="wt-h" className="text-lg font-bold">What matters to you?</h2><p className="text-sm text-muted">Change the weights and re-rank; the ordering updates from the same formula.</p>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">{W_KEYS.map((k) => (<div key={k}><label className="label capitalize" htmlFor={`w-${k}`}>{k} <span className="font-normal text-muted">{weights[k].toFixed(2)}</span></label><input id={`w-${k}`} type="range" min={0} max={1} step={0.05} className="w-full" value={weights[k]} onChange={(e) => setWeights({ ...weights, [k]: Number(e.target.value) })} /></div>))}</div>
              <button className="btn-primary mt-4" disabled={busy} onClick={() => void act(() => api(`/cases/${id}/rank`, { body: { weights } }), "Re-ranked.")}>Re-rank</button></section>
          </>)}

          {tab === "draft" && (<section className="card" aria-labelledby="dr-h"><div className="flex flex-wrap items-center justify-between gap-2"><h2 id="dr-h" className="text-lg font-bold">Draft complaint</h2>
              {c.draft && <div className="flex gap-2"><Tag>v{c.draft.version}</Tag><Tag tone={c.draft.status === "APPROVED" ? "teal" : "amber"}>{c.draft.status.toLowerCase()}</Tag><Tag>{c.draft.origin.replace("_", " ")}</Tag></div>}</div>
            {!c.draft ? <Empty title="No draft yet">{c.missing.length ? "Answer the questions on the Overview tab first." : "Re-run the analysis."}</Empty> : (<>
              <label className="sr-only" htmlFor="dbody">Draft text</label>
              <textarea id="dbody" className="input mt-3 min-h-[360px] resize-y py-3 font-mono text-[13px] leading-relaxed" disabled={locked} value={draft} onChange={(e) => { setDraft(e.target.value); setDraftDirty(true); }} />
              <p className="mt-2 text-xs text-muted">Citations in [kb_…] form must be among the retrieved sources; REDEEM refuses a citation it did not retrieve. Editing voids any approval.</p>
              {c.draft.cited.length > 0 && <p className="mt-1 text-xs">Cited: {c.draft.cited.map((x) => <code key={x} className="mr-2">{x}</code>)}</p>}
              {!locked && <div className="mt-4 flex flex-wrap gap-2"><button className="btn-ghost" disabled={busy || !draftDirty} onClick={() => void act(async () => { const v = await api<CaseView>(`/cases/${id}/draft`, { method: "PUT", body: { body: draft } }); setDraftDirty(false); return v; }, "Saved as a new version; approval cleared.")}>Save edits</button>
                {draftDirty && <button className="btn-ghost" onClick={() => { setDraft(c.draft!.body); setDraftDirty(false); }}>Discard edits</button>}</div>}
              {!locked && (<div className="mt-6 rounded-xl border border-line p-4"><h3 className="font-bold">Approve</h3><p className="text-sm text-muted">Your approval is bound to this exact draft, the facts, the provider and the chosen action. Change any of them and it is voided.</p>
                <div className="mt-3 flex flex-wrap items-end gap-3"><div><label className="label" htmlFor="ak">Action</label><select id="ak" className="input" value={actionKey} onChange={(e) => setActionKey(e.target.value)}>{c.ranking.ranked.map((r) => <option key={r.key} value={r.key}>{r.name.slice(0, 60)}</option>)}</select></div>
                  <button className="btn-teal" disabled={busy || draftDirty || c.missing.length > 0} onClick={() => void act(() => api(`/cases/${id}/approve`, { body: { action_key: actionKey, digest: c.draft!.approval_digests[actionKey] } }), "Approved.")}>Approve this draft</button></div>
                {draftDirty && <p className="mt-2 text-xs text-danger">Save or discard your edits first.</p>}{c.approval && <p className="mt-2 text-sm text-teal">Approved action: {c.approval.action_key} (draft v{c.approval.draft_version}) — {c.approval_valid ? "valid" : "no longer valid"}.</p>}</div>)}
              <div className="mt-6"><h3 className="text-sm font-bold">Version history</h3><ul className="mt-2 text-sm">{c.drafts.map((d) => <li key={d.version} className="flex gap-3 py-1"><span className="font-semibold">v{d.version}</span><span className="text-muted">{d.origin.replace("_", " ")}, {d.status.toLowerCase()}, {d.hash}, {when(d.created_at)}</span></li>)}</ul></div>
            </>)}</section>)}

          {tab === "track" && (<>
            <section className="card" aria-labelledby="sb-h"><h2 id="sb-h" className="text-lg font-bold">Submit</h2>
              {c.status === "APPROVED" && <button className="btn-primary mt-3" disabled={busy} onClick={() => void act(() => api(`/cases/${id}/submit`, { method: "POST" }), "Recorded and read back. Now file it with the authority.")}>Record and prepare handoff</button>}
              {c.status === "AWAITING_APPROVAL" && <p className="mt-2 text-sm text-muted">Approve the draft first (Draft &amp; approval tab).</p>}
              {c.handoff && (<div className="mt-3 rounded-xl bg-soft p-4 text-sm"><p className="font-semibold">{c.handoff.mode === "guided_handoff" ? "Guided handoff" : "Fixture airline desk"} — record {c.handoff.internal_record}</p><p className="mt-1">{c.handoff.statement}</p>
                {c.handoff.step && <p className="mt-2"><strong>File here:</strong> {c.handoff.step.text}</p>}{c.handoff.step?.links.map((l) => <a key={l} className="mr-3 text-xs font-semibold text-indigo underline" target="_blank" rel="noopener noreferrer" href={l}>{l.replace(/^https?:\/\//, "")}</a>)}
                {c.handoff.documents_to_attach.length > 0 && <p className="mt-2 text-xs text-muted">Attach: {c.handoff.documents_to_attach.join("; ")}</p>}</div>)}</section>
            {["SUBMITTED", "TRACKING"].includes(c.status) && (<section className="card" aria-labelledby="tr-h"><h2 id="tr-h" className="text-lg font-bold">Log what happens</h2>
              <div className="mt-3 grid gap-3 sm:grid-cols-2"><div><label className="label" htmlFor="tk">Update</label><select id="tk" className="input" value={track.kind} onChange={(e) => setTrack({ ...track, kind: e.target.value })}>{[["acknowledgement", "Acknowledged by the provider"], ["response", "Provider responded"], ["escalated", "I escalated"], ["resolved", "Resolved in my favour"], ["rejected", "Rejected / unresolved"]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
                <div><label className="label" htmlFor="tref">Reference / docket no.</label><input id="tref" className="input" value={track.reference} onChange={(e) => setTrack({ ...track, reference: e.target.value })} /></div>
                {["resolved"].includes(track.kind) && <div><label className="label" htmlFor="tamt">Amount received (₹)</label><input id="tamt" type="number" min="0" className="input" value={track.amount_inr} onChange={(e) => setTrack({ ...track, amount_inr: e.target.value })} /></div>}
                <div><label className="label" htmlFor="tdoc">Supporting document</label><select id="tdoc" className="input" value={track.document_id} onChange={(e) => setTrack({ ...track, document_id: e.target.value })}><option value="">None (user-reported only)</option>{vault.map((d) => <option key={d.id} value={d.id}>{d.filename}</option>)}</select></div>
                <div className="sm:col-span-2"><label className="label" htmlFor="tnote">Note</label><textarea id="tnote" className="input py-3" rows={2} value={track.note} onChange={(e) => setTrack({ ...track, note: e.target.value })} /></div></div>
              <p className="mt-2 text-xs text-muted">An outcome is only marked <strong>verified</strong> when a relevant document supports it; otherwise it is recorded as user-reported.</p>
              <button className="btn-primary mt-3" disabled={busy} onClick={() => void act(() => api(`/cases/${id}/track`, { body: { kind: track.kind, reference: track.reference || null, note: track.note, document_id: track.document_id || null, amount_inr: track.amount_inr ? Number(track.amount_inr) : null } }), "Logged.")}>Log update</button></section>)}
            {c.outcome && <section className="card"><h2 className="text-lg font-bold">Outcome</h2><p className="mt-1"><Tag tone={c.outcome.verification === "SUPPORTED_BY_DOCUMENT" ? "teal" : "amber"}>{c.outcome.verification.replaceAll("_", " ").toLowerCase()}</Tag> {c.outcome.kind}</p><p className="mt-2 text-sm">{c.outcome.statement}</p></section>}
            <section className="card"><h2 className="text-lg font-bold">Reports</h2><div className="mt-3 flex flex-wrap gap-2">
              <button className="btn-ghost" onClick={() => void dl(`/cases/${id}/report?format=md`, `case-${id}.md`, "text/markdown")}>Case report (readable)</button>
              <button className="btn-ghost" onClick={() => void dl(`/cases/${id}/report`, `case-${id}.json`, "application/json")}>Case report (JSON)</button>
              <button className="btn-ghost" onClick={() => void dl(`/cases/${id}/bundle`, `evidence-bundle-${id}.zip`, "application/zip")}>Evidence bundle (.zip)</button>
              {c.status !== "CLOSED" && locked && <button className="btn-ghost" disabled={busy} onClick={() => void act(() => api(`/cases/${id}/close`, { method: "POST" }), "Case closed.")}>Close case</button>}
              <button className="btn-ghost text-danger" disabled={busy} onClick={() => { if (confirm("Delete this case and its drafts? Documents stay in your vault.")) void act(async () => { await api(`/cases/${id}`, { method: "DELETE" }); router.push("/app/cases"); }); }}>Delete case</button></div></section>
          </>)}
        </div>

        <aside className="space-y-5" aria-label="Case timeline">
          <section className="card"><h2 className="text-base font-bold">Timeline</h2>
            <ol className="mt-3 max-h-[520px] space-y-2 overflow-y-auto text-sm">{[...c.events].reverse().map((e) => (<li key={e.seq} className="border-l-2 border-line pl-3"><p className="font-semibold">{e.type === "STAGE" ? String(e.data.stage).replaceAll("_", " ").toLowerCase() : e.type.replaceAll("_", " ").toLowerCase()}</p><p className="text-xs text-muted">{when(e.at)}</p></li>))}</ol></section>
        </aside>
      </div>
    </div>
  );
}
