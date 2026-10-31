"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Empty, ErrorNote, PageTitle, Tag } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

type Step = { op: "goto" | "fill" | "click" | "wait_text"; app?: string; path?: string; label?: string; value?: string; button?: string; text?: string };
type Skill = { id: string; name: string; steps: Step[]; params: string[]; runs: number; last_status: string | null; created_at: string };
type Frame = { id: string; phase: string; label: string; url: string; title: string; screenshot_url: string; screenshot_sha: string; at: string };
type Run = { id: string; skill_id: string | null; status: string; step_index: number; total_steps: number; error: string | null; uncertain: boolean; frames: Frame[] };

const LIVE = ["QUEUED", "RUNNING", "PAUSED"];
const TONE: Record<string, "teal" | "amber" | "danger" | "soft"> = { DONE: "teal", RUNNING: "amber", PAUSED: "amber", QUEUED: "soft", FAILED: "danger", STOPPED: "danger", USER_ACTION_REQUIRED: "amber" };
const EXAMPLE: Step[] = [
  { op: "goto", app: "crm", path: "/" }, { op: "wait_text", text: "Create follow-up task" },
  { op: "fill", label: "Contact ID", value: "{{contact}}" }, { op: "fill", label: "Task title", value: "{{title}}" },
  { op: "click", button: "Create task" }, { op: "wait_text", text: "Task created" },
];
const describe = (s: Step) => s.op === "goto" ? `Open ${s.app}${s.path}` : s.op === "fill" ? `Type “${s.value}” into ${s.label}` : s.op === "click" ? `Click ${s.button}` : `Wait for “${s.text}”`;
const paramsOf = (steps: Step[]) => Array.from(new Set(steps.flatMap((s) => Array.from((s.value || "").matchAll(/\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}/g)).map((m) => m[1]))));

function Frames({ run }: { run: Run }) {
  const [sel, setSel] = useState<string | null>(null);
  const f = run.frames.find((x) => x.id === sel) ?? run.frames[run.frames.length - 1];
  return (
    <div className="grid gap-3 md:grid-cols-[1fr_220px]">
      <div className="overflow-hidden rounded-xl border border-line bg-soft">
        {f ? (<>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={f.screenshot_url} alt={`Browser screenshot: ${f.label}`} className="w-full" />
          <p className="border-t border-line px-3 py-2 text-xs text-muted"><span className="font-semibold text-ink">{f.label}</span> · {f.url} · sha256 {f.screenshot_sha.slice(0, 12)}</p>
        </>) : <p className="p-6 text-sm text-muted">{LIVE.includes(run.status) ? "Starting Chromium… the first frame appears after the first step." : "No frames were captured."}</p>}
      </div>
      <ol className="max-h-[420px] space-y-1 overflow-auto text-sm" aria-label="Captured frames">
        {run.frames.map((x) => (<li key={x.id}><button onClick={() => setSel(x.id)} className={`w-full rounded-lg px-3 py-2 text-left ${f?.id === x.id ? "bg-soft font-semibold" : "hover:bg-soft"}`}>{x.label}<span className="block text-xs text-muted">{x.phase}</span></button></li>))}
      </ol>
    </div>
  );
}

export default function Skills() {
  const [items, setItems] = useState<Skill[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("CRM follow-up task");
  const [json, setJson] = useState(JSON.stringify(EXAMPLE, null, 2));
  const [vals, setVals] = useState<Record<string, string>>({ contact: "C-104", title: "Call back about the refund" });
  const [busy, setBusy] = useState(false);
  const [run, setRun] = useState<Run | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => { try { setItems((await api<{ items: Skill[] }>("/browser/skills")).items); } catch (e) { setError(e instanceof ApiError ? e.message : "Could not load skills"); } }, []);
  useEffect(() => { void load(); return () => { if (timer.current) clearTimeout(timer.current); }; }, [load]);

  const poll = useCallback((id: string) => {
    const tick = async () => {
      try {
        const r = await api<Run>(`/browser/skill-runs/${id}`); setRun(r);
        if (LIVE.includes(r.status)) timer.current = setTimeout(tick, 700); else void load();
      } catch (e) { setError(e instanceof ApiError ? e.message : "Lost the run"); }
    };
    void tick();
  }, [load]);

  let steps: Step[] = []; let parseErr: string | null = null;
  try { steps = JSON.parse(json); if (!Array.isArray(steps)) throw new Error("Steps must be a JSON array"); } catch (e) { parseErr = (e as Error).message; }
  const params = parseErr ? [] : paramsOf(steps);

  const record = async () => {
    setBusy(true); setError(null); setRun(null);
    try { const r = await api<{ skill: Skill | null; recording: Run }>("/browser/skills/record", { method: "POST", body: { name, steps, params: vals } }); setRun(r.recording); if (!r.skill) setError(`Not saved: the recording ${r.recording.status.toLowerCase()} (${r.recording.error ?? "no detail"}).`); await load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Recording failed"); } finally { setBusy(false); }
  };
  const replay = async (s: Skill) => {
    setError(null);
    try { const r = await api<Run>(`/browser/skills/${s.id}/run`, { method: "POST", body: { params: vals } }); setRun(r); poll(r.id); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Could not start"); }
  };
  const ctl = async (action: "pause" | "resume" | "stop") => { if (!run) return; try { await api(`/browser/skill-runs/${run.id}/control`, { method: "POST", body: { action } }); } catch (e) { setError(e instanceof ApiError ? e.message : "Control failed"); } };
  const remove = async (s: Skill) => { try { await api(`/browser/skills/${s.id}`, { method: "DELETE" }); await load(); } catch (e) { setError(e instanceof ApiError ? e.message : "Delete failed"); } };

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageTitle title="Browser skills" sub="Record a browser workflow by doing it once in a real Chromium session, then replay it and watch every step live. Runs only on REDEEM's local practice apps (CRM, report store, outbox); the browser cannot reach any other site." />
      <ErrorNote error={error} />
      <section className="card space-y-3" aria-labelledby="rec-h">
        <h2 id="rec-h" className="text-lg font-bold">Record a skill</h2>
        <label className="block text-sm font-semibold">Name<input className="input mt-1 w-full" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} /></label>
        <div className="grid gap-4 md:grid-cols-2">
          <label className="block text-sm font-semibold">Steps (JSON)<textarea className="input mt-1 h-64 w-full font-mono text-xs" value={json} onChange={(e) => setJson(e.target.value)} spellCheck={false} aria-describedby="steps-help" /></label>
          <div>
            <p id="steps-help" className="text-xs text-muted">Ops: <code>goto</code> (app: crm, docs, outbox), <code>fill</code> (label, value), <code>click</code> (button), <code>wait_text</code> (text). Use <code>{"{{name}}"}</code> for values you supply at run time.</p>
            {parseErr ? <p className="mt-2 text-sm text-danger">{parseErr}</p> : <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm">{steps.map((s, i) => <li key={i}>{describe(s)}</li>)}</ol>}
            {params.length > 0 && <div className="mt-3 space-y-2">{params.map((p) => (<label key={p} className="block text-sm font-semibold">{p}<input className="input mt-1 w-full" value={vals[p] ?? ""} onChange={(e) => setVals({ ...vals, [p]: e.target.value })} /></label>))}</div>}
          </div>
        </div>
        <button className="btn-primary" disabled={busy || !!parseErr || !name.trim()} onClick={record}>{busy ? "Recording in Chromium…" : "Record by running once"}</button>
        <p className="text-xs text-muted">The skill is saved only if every step succeeds. A step that needs a password, CAPTCHA, one-time code or payment stops the run for you to do yourself.</p>
      </section>

      {run && (
        <section className="card space-y-3" aria-labelledby="run-h" aria-live="polite">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 id="run-h" className="text-lg font-bold">Run {run.id}</h2>
            <div className="flex items-center gap-2"><Tag tone={TONE[run.status] ?? "soft"}>{run.status.replaceAll("_", " ").toLowerCase()}</Tag><span className="text-sm tabular-nums text-muted">step {run.step_index} of {run.total_steps}</span></div>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-soft" role="progressbar" aria-valuemin={0} aria-valuemax={run.total_steps} aria-valuenow={run.step_index}><div className={`h-full ${run.status === "DONE" ? "bg-teal" : ["FAILED", "STOPPED"].includes(run.status) ? "bg-danger" : "bg-accent"}`} style={{ width: `${run.total_steps ? (100 * run.step_index) / run.total_steps : 0}%` }} /></div>
          {LIVE.includes(run.status) && <div className="flex gap-2">{run.status === "PAUSED" ? <button className="btn-ghost" onClick={() => ctl("resume")}>Resume</button> : <button className="btn-ghost" onClick={() => ctl("pause")}>Pause</button>}<button className="btn-ghost" onClick={() => ctl("stop")}>Stop</button></div>}
          {run.error && <p className="text-sm text-danger">{run.error}</p>}
          {run.uncertain && <p className="rounded-lg bg-soft px-3 py-2 text-sm">A button was clicked before the run ended, so the app may already have changed. Check it before running again; REDEEM does not retry on its own.</p>}
          <Frames run={run} />
        </section>
      )}

      <section aria-labelledby="lib-h" className="space-y-3">
        <h2 id="lib-h" className="text-lg font-bold">Saved skills</h2>
        {items.length === 0 ? <Empty title="No skills yet">Record one above.</Empty> : (
          <ul className="grid gap-3 md:grid-cols-2">{items.map((s) => (
            <li key={s.id} className="card space-y-2">
              <div className="flex items-start justify-between gap-2"><h3 className="font-bold">{s.name}</h3>{s.last_status && <Tag tone={TONE[s.last_status] ?? "soft"}>{s.last_status.replaceAll("_", " ").toLowerCase()}</Tag>}</div>
              <p className="text-xs text-muted">{s.steps.length} steps · {s.runs} runs{s.params.length ? ` · needs ${s.params.join(", ")}` : ""}</p>
              <div className="flex gap-2"><button className="btn-primary" disabled={!!run && LIVE.includes(run.status)} onClick={() => replay(s)}>Run and watch</button><button className="btn-ghost" onClick={() => remove(s)}>Delete</button></div>
            </li>))}</ul>)}
      </section>
    </div>
  );
}
