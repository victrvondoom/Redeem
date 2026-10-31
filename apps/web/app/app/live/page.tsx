"use client";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ErrorNote, PageTitle, Tag } from "@/components/ui";
import { Tilt } from "@/components/Cinematic";
import { api, ApiError } from "@/lib/api";

type Ev = { seq: number; type: string; action_id: string | null; data: Record<string, unknown>; created_at: string };
type Task = { id: string; kind: string; owner: string; mode: string; depends_on: string[]; status: string; action_id: string | null };
type Mission = { id: string; status: string; intent?: string; plan?: { actions: { id: string; label?: string; type?: string }[] } };
const SCEN: [string, string, string][] = [["a", "Flight recovery", "refund + hotel + calendar + family draft"], ["b", "Shop reservation", "atomic stock reservation"], ["d", "Browser operator", "real Chromium on fixture CRM"], ["c", "Adversarial recovery", "stale approval, lost ACK"]];
const SPEEDS = [0.5, 1, 2, 4];
const GOOD = new Set(["VERIFIED", "RECEIPT", "ACKED", "RECONCILED"]);

function layout(tasks: Task[]) {
  const depth: Record<string, number> = {};
  const get = (t: Task): number => depth[t.id] ??= t.depends_on.length ? 1 + Math.max(...t.depends_on.map((d) => { const p = tasks.find((x) => x.id === d); return p ? get(p) : 0; })) : 0;
  tasks.forEach(get);
  const cols: Record<number, Task[]> = {};
  tasks.forEach((t) => (cols[depth[t.id]] ??= []).push(t));
  const pos: Record<string, { x: number; y: number }> = {};
  Object.entries(cols).forEach(([c, ts]) => ts.forEach((t, i) => (pos[t.id] = { x: Number(c) * 154 + 8, y: i * 62 + 8 })));
  const W = (Math.max(...Object.keys(cols).map(Number), 0) + 1) * 154 + 8, H = Math.max(...Object.values(cols).map((c) => c.length), 1) * 62 + 16;
  return { pos, W, H };
}

export default function Live() {
  const [scn, setScn] = useState("a");
  const [mission, setMission] = useState<Mission | null>(null);
  const [events, setEvents] = useState<Ev[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [cur, setCur] = useState(0);
  const [play, setPlay] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const feed = useRef<HTMLOListElement>(null);

  const run = useCallback(async () => {
    setBusy(true); setError(null); setPlay(false); setCur(0);
    try {
      const out = await api<{ mission_id: string }>(`/demo/scenarios/${scn}/run`, { method: "POST" });
      const [m, e, t] = await Promise.all([api<Mission>(`/missions/${out.mission_id}`), api<{ items: Ev[] }>(`/missions/${out.mission_id}/events?limit=500`), api<{ items: Task[] }>(`/missions/${out.mission_id}/tasks`)]);
      setMission(m); setEvents(e.items); setTasks(t.items); setPlay(true);
    } catch (x) { setError(x instanceof ApiError ? x.message : "Run failed"); } finally { setBusy(false); }
  }, [scn]);

  useEffect(() => {
    if (!play) return;
    if (cur >= events.length) { setPlay(false); return; }
    const t = setTimeout(() => setCur((c) => c + 1), 520 / speed);
    return () => clearTimeout(t);
  }, [play, cur, events.length, speed]);
  useEffect(() => { feed.current?.scrollTo({ top: feed.current.scrollHeight, behavior: "smooth" }); }, [cur]);

  const seen = events.slice(0, cur);
  const first = useMemo(() => { const m = new Map<string, number>(); events.forEach((e, i) => { if (e.action_id && !m.has(e.action_id)) m.set(e.action_id, i); }); return m; }, [events]);
  const verified = useMemo(() => { const m = new Map<string, number>(); events.forEach((e, i) => { if (e.action_id && (e.type === "VERIFIED" || e.type === "RECONCILED")) m.set(e.action_id, i); }); return m; }, [events]);
  const readsAt = events.findIndex((e) => e.type === "READS_COMPLETED");
  const g = useMemo(() => layout(tasks), [tasks]);
  const state = (t: Task): "idle" | "active" | "done" => {
    if (t.action_id) { const v = verified.get(t.action_id), f = first.get(t.action_id); if (v !== undefined && cur > v) return "done"; return f !== undefined && cur > f ? "active" : "idle"; }
    return readsAt >= 0 && cur > readsAt ? "done" : cur > 0 ? "active" : "idle";
  };
  const doneN = tasks.filter((t) => state(t) === "done").length;
  const finished = events.length > 0 && cur >= events.length;
  const last = seen[seen.length - 1];

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageTitle title="Live Engine" sub="Run a real mission through the engine, then watch it play back from its append-only ledger: tasks light up as the events that prove them arrive. Fixture providers only." />
      <ErrorNote error={error} />
      <div className="card flex flex-wrap items-center gap-3 !p-4">
        <div role="radiogroup" aria-label="Scenario" className="flex flex-wrap gap-2">
          {SCEN.map(([id, name, sub]) => (<button key={id} role="radio" aria-checked={scn === id} onClick={() => setScn(id)} title={sub}
            className={`min-h-[44px] rounded-xl border px-4 text-sm font-semibold transition-colors ${scn === id ? "border-teal bg-teal-soft text-teal" : "border-line text-muted hover:text-ink"}`}>{name}</button>))}
        </div>
        <button className="btn-primary ml-auto" disabled={busy} onClick={() => void run()}>{busy ? "Running engine…" : mission ? "Run again" : "Run live"}</button>
      </div>

      {!mission ? (
        <div className="card text-center"><p className="text-lg font-bold">Pick a scenario and press Run live.</p><p className="mt-1 text-sm text-muted">Nothing here is pre-recorded: the run executes now, and the ledger you watch is read from the database.</p></div>
      ) : (<>
        <div className="grid gap-6 lg:grid-cols-1">
          <Tilt max={4} className="card !p-0 overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3"><span className="text-sm font-semibold text-teal">Task graph</span>
              <span className="text-xs text-muted">{doneN}/{tasks.length} tasks verified</span></div>
            <div className="overflow-x-auto p-3"><svg role="img" aria-label="Mission task graph" viewBox={`0 0 ${g.W} ${g.H}`} className="h-auto w-full">
              {tasks.flatMap((t) => t.depends_on.map((d) => { const a = g.pos[d], b = g.pos[t.id]; if (!a || !b) return null; const on = state(t) !== "idle";
                return <path key={`${d}-${t.id}`} d={`M${a.x + 140} ${a.y + 24} C ${a.x + 150} ${a.y + 24}, ${b.x - 10} ${b.y + 24}, ${b.x} ${b.y + 24}`} fill="none" stroke={on ? "rgb(255 122 26)" : "rgb(52 47 44)"} strokeWidth={on ? 2 : 1} style={{ transition: "stroke .4s, stroke-width .4s" }} />; }))}
              {tasks.map((t) => { const p = g.pos[t.id], s = state(t); return (
                <g key={t.id} transform={`translate(${p.x},${p.y})`}><g className={s !== "idle" ? "node-pop" : ""} style={{ transformBox: "fill-box", transformOrigin: "center" }}>
                  <rect width="140" height="48" rx="11" fill={s === "done" ? "rgb(8 44 22)" : s === "active" ? "rgb(52 26 8)" : "rgb(9 14 11)"} stroke={s === "idle" ? "rgb(34 52 41)" : s === "done" ? "rgb(52 211 102)" : "rgb(255 122 26)"} strokeWidth={s === "active" ? 2 : 1} style={{ filter: undefined }} />
                  <text x="10" y="20" fontSize="12" fontWeight="700" fill={s === "idle" ? "rgb(160 152 146)" : "rgb(240 236 232)"}>{t.kind.length > 17 ? t.kind.slice(0, 16) + "…" : t.kind}</text>
                  <text x="10" y="37" fontSize="10" fill="rgb(160 152 146)">{t.owner}, {s === "done" ? "verified ✓" : s === "active" ? "working…" : "waiting"}</text>
                </g></g>); })}
            </svg></div>
          </Tilt>

          <div className="card !p-0">
            <div className="flex items-center justify-between border-b border-line px-4 py-3"><span className="text-sm font-semibold text-teal">Ledger, {Math.min(cur, events.length)} of {events.length}</span><span className="text-xs text-muted">hash-chained, append-only</span></div>
            <ol ref={feed} className="h-[260px] space-y-1 overflow-y-auto p-3 font-mono text-[12px]" aria-label="Ledger events">
              {seen.map((e) => (<li key={e.seq} className="ticker-in flex gap-2 rounded-lg px-2 py-1 hover:bg-soft"><span className="w-7 shrink-0 text-muted">{e.seq}</span><span className={`shrink-0 font-bold ${GOOD.has(e.type) ? "text-teal" : "text-ink"}`}>{e.type}</span><span className="truncate text-muted">{JSON.stringify(e.data).slice(0, 90)}</span></li>))}
              {cur === 0 && <li className="p-2 text-muted">Press play…</li>}
            </ol>
          </div>
        </div>

        <div className="card flex flex-wrap items-center gap-3 !p-4">
          <button className="btn-ghost !min-h-[40px]" onClick={() => { if (finished) setCur(0); setPlay((p) => !p || finished); }} aria-label={play ? "Pause playback" : "Play"}>{play ? "❚❚ Pause" : finished ? "↺ Replay" : "▶ Play"}</button>
          <input type="range" min={0} max={events.length} value={cur} onChange={(e) => { setPlay(false); setCur(Number(e.target.value)); }} aria-label="Playback position" className="min-w-[160px] flex-1 accent-[rgb(255,122,26)]" />
          <div role="group" aria-label="Speed" className="flex gap-1">{SPEEDS.map((s) => <button key={s} onClick={() => setSpeed(s)} aria-pressed={speed === s} className={`badge min-h-[32px] ${speed === s ? "bg-teal text-deep" : "bg-soft text-muted"}`}>{s}×</button>)}</div>
        </div>

        <div className="card" aria-live="polite">
          <div className="flex flex-wrap items-center gap-3"><h2 className="text-lg font-bold">Outcome</h2>
            <Tag tone={finished ? (mission.status === "VERIFIED" ? "teal" : "amber") : "soft"}>{finished ? mission.status : "in progress"}</Tag>
            {last && <span className="text-sm text-muted">now: <span className="font-mono text-ink">{last.type}</span></span>}</div>
          {finished && <p className="mt-2 text-sm text-muted">The engine finished and read the result back independently. <Link className="font-semibold text-teal" href={`/app/missions/${mission.id}`}>Open the mission, evidence and receipt</Link></p>}
        </div>
      </>)}
    </div>
  );
}
