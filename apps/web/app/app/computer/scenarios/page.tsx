"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ErrorNote, PageTitle, Tag } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

type Run = { task_id: string; status: string; started_at: string; completed_at: string | null; verification_status: string | null; summary: string | null; scenario_version?: number };
type Prop = { type?: string; enum?: string[]; description?: string };
type Scenario = {
  id: string; key: string; name: string; description: string; category: string; enabled: boolean; version: number; required_os: string; required_capabilities: string[];
  built_in: boolean; runnable: boolean; unavailable_reason: string | null; run_count: number; last_run: Run | null;
  parameter_schema: { required?: string[]; properties?: Record<string, Prop> };
};
type Detail = Scenario & { steps: { op: string; target?: string; app?: string; keys?: string; when?: string }[]; expected_result: string; verification: string[]; approvals: string[] };
type Catalog = { items: Scenario[]; categories: string[]; operating_systems: string[] };
type Sess = { id: string; device_id: string; status: string; mode: string };

const TONE: Record<string, "teal" | "amber" | "danger" | "soft"> = { completed: "teal", running: "amber", queued: "amber", paused: "amber", waiting_for_approval: "amber", failed: "danger", cancelled: "danger", outcome_uncertain: "danger", needs_input: "amber" };
const LABEL = (s: string) => s.replace(/_/g, " ");

export default function Scenarios() {
  const [cat, setCat] = useState<Catalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [os, setOs] = useState("");
  const [open, setOpen] = useState<Detail | null>(null);
  const [runs, setRuns] = useState<(Run & { instruction: string })[]>([]);
  const [params, setParams] = useState<Record<string, string>>({});
  const [sessions, setSessions] = useState<Sess[]>([]);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    const qs = new URLSearchParams();
    if (q) qs.set("q", q);
    if (category) qs.set("category", category);
    if (os) qs.set("os", os);
    try { setCat(await api<Catalog>(`/computer/scenarios?${qs}`)); setError(null); } catch (e) { setError(e instanceof ApiError ? e.message : "Could not load scenarios"); }
  }, [q, category, os]);
  useEffect(() => { void load(); const t = setInterval(() => void load(), 3000); return () => clearInterval(t); }, [load]); // task changes are persisted; refresh reflects them
  useEffect(() => { void api<{ items: Sess[] }>("/computer/sessions").then((r) => setSessions(r.items.filter((s) => s.status === "ACTIVE"))).catch(() => undefined); }, []);

  const select = async (key: string) => {
    setMsg(null); setParams({});
    try {
      setOpen(await api<Detail>(`/computer/scenarios/${key}`));
      setRuns((await api<{ items: (Run & { instruction: string })[] }>(`/computer/scenarios/${key}/runs`)).items);
    } catch (e) { setError(e instanceof ApiError ? e.message : "Could not load the scenario"); }
  };
  const run = async () => {
    if (!open) return;
    const s = sessions[0];
    if (!s) { setMsg("Open a computer session on the Live Computer page first."); return; }
    const props = open.parameter_schema.properties ?? {};
    const body: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(params)) if (v !== "") body[k] = props[k]?.type === "boolean" ? v === "true" : v;
    try {
      const r = await api<{ id: string }>(`/computer/scenarios/${open.key}/run`, { method: "POST", body: { session_id: s.id, params: body } });
      setMsg(`Started task ${r.id}. Follow it on the Live Computer page.`);
      await load(); await select(open.key);
    } catch (e) { setMsg(e instanceof ApiError ? e.message : "Could not start"); }
  };
  const shown = useMemo(() => cat?.items ?? [], [cat]);

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <PageTitle title="Computer scenarios" />
      <p className="text-sm text-muted">Scenarios come from the database. The last run is the newest real task for that scenario; “Never run” means no task exists.</p>
      <div className="flex flex-wrap gap-2">
        <input className="input" placeholder="Search scenarios" aria-label="Search scenarios" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className="input" aria-label="Category" value={category} onChange={(e) => setCategory(e.target.value)}><option value="">All categories</option>{cat?.categories.map((c) => <option key={c}>{c}</option>)}</select>
        <select className="input" aria-label="Operating system" value={os} onChange={(e) => setOs(e.target.value)}><option value="">Any operating system</option>{cat?.operating_systems.filter((o) => o !== "any").map((o) => <option key={o}>{o}</option>)}</select>
      </div>
      <ErrorNote error={error} />
      {!cat && !error && <p className="text-sm text-muted">Loading scenarios…</p>}
      {cat && shown.length === 0 && <p className="text-sm text-muted">No scenarios match.</p>}
      <ul className="grid gap-3 md:grid-cols-2">{shown.map((s) => (
        <li key={s.id} className="card">
          <button className="w-full text-left" onClick={() => void select(s.key)}>
            <h2 className="font-bold">{s.name}</h2>
            <p className="text-xs text-muted">{s.category} · {s.required_os === "any" ? "any OS" : s.required_os} · v{s.version}{s.built_in ? " · built-in" : ""}</p>
            <p className="mt-1 text-sm">{s.description}</p>
          </button>
          <div className="mt-2 flex items-center gap-2 text-xs">
            {s.last_run ? <><Tag tone={TONE[s.last_run.status] ?? "soft"}>{LABEL(s.last_run.status)}</Tag><span className="text-muted">{new Date(s.last_run.started_at).toLocaleString()}</span></> : <Tag tone="soft">Never run</Tag>}
            {!s.runnable && <Tag tone="soft">not runnable</Tag>}
          </div>
        </li>))}</ul>
      {open && (
        <section className="card space-y-3" aria-label="Scenario detail">
          <h2 className="text-lg font-bold">{open.name} <span className="text-xs text-muted">v{open.version}</span></h2>
          <p className="text-sm">{open.expected_result}</p>
          <div className="text-xs text-muted">Needs: {open.required_capabilities.join(", ") || "nothing special"} · OS: {open.required_os}</div>
          <ol className="list-decimal pl-5 text-sm">{open.steps.map((st, i) => <li key={i}>{st.op}{st.target ? ` — ${st.target}` : ""}{st.when ? ` (${st.when})` : ""}</li>)}</ol>
          {open.approvals.length > 0 && <p className="text-sm">Approval needed for: {open.approvals.join("; ")}</p>}
          {open.verification.length > 0 && <p className="text-sm">Verified by: {open.verification.join("; ")}</p>}
          {open.runnable ? (
            <div className="space-y-2">
              {Object.entries(open.parameter_schema.properties ?? {}).map(([k, p]) => (
                <label key={k} className="block text-sm">{k}{open.parameter_schema.required?.includes(k) ? " *" : ""}{" "}
                  {p.enum ? <select className="input" value={params[k] ?? ""} onChange={(e) => setParams({ ...params, [k]: e.target.value })}><option value="">—</option>{p.enum.map((v) => <option key={v}>{v}</option>)}</select>
                    : p.type === "boolean" ? <select className="input" value={params[k] ?? ""} onChange={(e) => setParams({ ...params, [k]: e.target.value })}><option value="">—</option><option value="true">yes</option><option value="false">no</option></select>
                    : <input className="input" value={params[k] ?? ""} onChange={(e) => setParams({ ...params, [k]: e.target.value })} />}</label>))}
              <button className="btn" onClick={() => void run()}>Run on my computer</button>
              {sessions.length === 0 && <span className="ml-2 text-xs text-muted">No active computer session.</span>}
            </div>
          ) : <p className="text-sm text-muted">{open.unavailable_reason}</p>}
          {msg && <p className="text-sm" role="status">{msg}</p>}
          <h3 className="font-bold">Execution history</h3>
          {runs.length === 0 ? <p className="text-sm text-muted">Never run.</p> : (
            <ul className="space-y-1 text-sm">{runs.map((r) => <li key={r.task_id}><Tag tone={TONE[r.status] ?? "soft"}>{LABEL(r.status)}</Tag> {new Date(r.started_at).toLocaleString()} · task {r.task_id}{r.verification_status ? ` · ${LABEL(r.verification_status)}` : ""}{r.summary ? ` — ${r.summary}` : ""}</li>)}</ul>)}
        </section>)}
    </div>
  );
}
