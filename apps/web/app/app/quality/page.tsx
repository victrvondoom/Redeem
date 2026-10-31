"use client";
import { useEffect, useState } from "react";
import { ErrorNote, PageTitle, Tag } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { when } from "@/lib/format";

type Row = { n: number; correct_outcome: number; verified_outcome: number; wrong_target: number; duplicate: number; false_success: number; unauthorized_execution: number };
type Bench = { generated_at: string; seed: number; trials_per_cell: number; scope: string; caveat: string; ablations?: string; summary: Record<string, { TOTAL: Row }> };
type Run = { id: string; seed: number; trials_per_cell: number; status: string; duration_seconds: number | null; error: string | null; started_at: string; summary: Record<string, { TOTAL: Row }>; mode: string };
type Q = { benchmark: Bench | null; fixture_results: Record<string, unknown> & { label: string; language_breakdown: Record<string, { missions: number; verified: number }>; missions_by_status: Record<string, number> };
  live_provider_results: Record<string, unknown> & { label: string; note: string } };
const show = (v: unknown) => (v === null || v === undefined ? "Not measured" : typeof v === "object" ? (Object.keys(v as object).length ? JSON.stringify(v) : "None yet") : String(v));

export default function Quality() {
  const [q, setQ] = useState<Q | null>(null); const [error, setError] = useState<string | null>(null);
  const [runs, setRuns] = useState<Run[]>([]); const [running, setRunning] = useState(false); const [seed, setSeed] = useState(7); const [n, setN] = useState(3);
  useEffect(() => { api<Q>("/quality").then(setQ).catch((e) => setError(e.message)); api<{ items: Run[] }>("/quality/runs").then((r) => setRuns(r.items)).catch(() => undefined); }, []);
  const runBench = async () => { setRunning(true); setError(null); try { const r = await api<Run>("/quality/runs", { body: { seed, n } }); setRuns((x) => [r, ...x]); } catch (e) { setError(e instanceof ApiError ? e.message : "Run failed"); } finally { setRunning(false); } };
  const rows = (o: Record<string, unknown>, skip: string[]) => Object.entries(o).filter(([k]) => !skip.includes(k));
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageTitle title="Quality Lab" sub="Computed from this workspace’s real events. Anything REDEEM cannot measure says so." />
      <ErrorNote error={error} />
      <section className="card" aria-labelledby="run-h"><h2 id="run-h" className="text-lg font-bold">Run a deterministic benchmark</h2>
        <p className="mt-1 text-sm text-muted">Runs 7 fault scenarios × your seed count × 6 policies in a separate process and database, then stores the raw trials. Same seed, same result. Fixture-only.</p>
        <div className="mt-3 flex flex-wrap items-end gap-3"><div><label className="label" htmlFor="sd">Seed</label><input id="sd" type="number" min={0} className="input w-28" value={seed} onChange={(e) => setSeed(Number(e.target.value))} /></div>
          <div><label className="label" htmlFor="nn">Trials per cell</label><input id="nn" type="number" min={1} max={10} className="input w-28" value={n} onChange={(e) => setN(Number(e.target.value))} /></div>
          <button className="btn-primary" disabled={running} onClick={() => void runBench()}>{running ? "Running… (up to a minute)" : "Run benchmark"}</button></div>
        {runs.length > 0 && <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[640px] text-sm"><thead><tr className="border-b border-line text-left text-muted"><th className="py-2 pr-3">Run</th><th className="pr-3">Seed × n</th><th className="pr-3">Took</th><th className="pr-3">REDEEM correct</th><th className="pr-3">Naive correct</th><th className="pr-3">Naive false success</th><th>Raw</th></tr></thead>
          <tbody>{runs.map((r) => (<tr key={r.id} className="border-b border-line"><td className="py-2 pr-3"><code className="text-xs">{r.id}</code><br /><span className="text-xs text-muted">{when(r.started_at)}</span></td><td className="pr-3">{r.seed} × {r.trials_per_cell}</td><td className="pr-3">{r.duration_seconds}s</td>
            <td className="pr-3">{r.status === "DONE" ? `${r.summary.C_redeem.TOTAL.correct_outcome}/${r.summary.C_redeem.TOTAL.n}` : r.status.toLowerCase()}</td><td className="pr-3">{r.status === "DONE" ? `${r.summary.A_naive.TOTAL.correct_outcome}/${r.summary.A_naive.TOTAL.n}` : "—"}</td><td className="pr-3">{r.status === "DONE" ? `${r.summary.A_naive.TOTAL.false_success}/${r.summary.A_naive.TOTAL.n}` : "—"}</td>
            <td>{r.status === "DONE" ? <a className="font-semibold text-indigo underline" href={`/api/v1/quality/runs/${r.id}/raw`}>JSON</a> : <span className="text-danger text-xs">{r.error}</span>}</td></tr>))}</tbody></table></div>}</section>
      {q && (<>
        {q.benchmark && (<section className="card" aria-labelledby="bm-h"><div className="flex flex-wrap items-center gap-2"><h2 id="bm-h" className="text-lg font-bold">Policy benchmark &amp; ablations</h2><Tag tone="indigo">Local fixtures</Tag></div>
          <p className="mt-1 text-sm text-muted">Seed {q.benchmark.seed}, {q.benchmark.trials_per_cell} trials per scenario per policy, generated {q.benchmark.generated_at.slice(0, 10)}. {q.benchmark.scope}.</p>
          <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[640px] text-sm"><thead><tr className="border-b border-line text-left text-muted">
            {["Policy", "n", "Correct", "Verified", "Wrong target", "Duplicates", "False success", "Unauthorized"].map((h) => <th key={h} className="py-2 pr-3 font-semibold">{h}</th>)}</tr></thead>
            <tbody>{Object.entries(q.benchmark.summary).map(([name, v]) => (<tr key={name} className="border-b border-line"><td className="py-2 pr-3 font-semibold">{name.replaceAll("_", " ")}</td>
              <td className="pr-3">{v.TOTAL.n}</td><td className="pr-3">{v.TOTAL.correct_outcome}/{v.TOTAL.n}</td><td className="pr-3">{v.TOTAL.verified_outcome}</td><td className="pr-3">{v.TOTAL.wrong_target}</td><td className="pr-3">{v.TOTAL.duplicate}</td><td className="pr-3">{v.TOTAL.false_success}</td><td className="pr-3">{v.TOTAL.unauthorized_execution}</td></tr>))}</tbody></table></div>
          <div className="mt-4 space-y-2" aria-label="Correct outcomes by policy">{Object.entries(q.benchmark.summary).map(([name, v]) => (<div key={name} className="flex items-center gap-3 text-xs"><span className="w-36 shrink-0 text-muted">{name.replaceAll("_", " ")}</span>
            <div className="h-3 flex-1 overflow-hidden rounded-full bg-soft"><div className="h-full bg-teal" style={{ width: `${(100 * v.TOTAL.correct_outcome) / v.TOTAL.n}%` }} /></div><span className="w-12 text-right">{Math.round((100 * v.TOTAL.correct_outcome) / v.TOTAL.n)}%</span></div>))}</div>
          <p className="mt-3 text-xs text-muted">How to read: <em>C minus verifier</em> ≈ multi-agent execution without independent verification; <em>C minus reconcile</em> ≈ verification without recovery; <em>C redeem</em> = verification + recovery; <em>A/B</em> = single-executor baselines. Seven scenarios incl. revoked connector and cross-domain dependency failure.</p>
          <p className="mt-1 text-xs text-muted">{q.benchmark.ablations}</p><p className="mt-1 text-xs text-muted">{q.benchmark.caveat}</p></section>)}
        <section className="card"><div className="flex flex-wrap items-center gap-2"><h2 className="text-lg font-bold">Mission reliability</h2><Tag tone="indigo">Local fixtures</Tag></div>
          <p className="mt-1 text-sm text-muted">{q.fixture_results.label}</p>
          <dl className="mt-4 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">{rows(q.fixture_results, ["label", "language_breakdown", "missions_by_status"]).map(([k, v]) => (
            <div key={k} className="flex justify-between border-b border-line py-1.5"><dt className="text-muted">{k.replaceAll("_", " ")}</dt><dd className="font-semibold">{show(v)}</dd></div>))}</dl>
          <h3 className="mt-5 font-semibold">By language detected</h3>
          <p className="text-sm text-muted">{Object.entries(q.fixture_results.language_breakdown).map(([l, v]) => `${l}: ${v.verified}/${v.missions} verified`).join(", ") || "No missions yet"}</p></section>
        <section className="card"><div className="flex flex-wrap items-center gap-2"><h2 className="text-lg font-bold">Voice calls</h2><Tag tone="amber">Live provider</Tag></div>
          <p className="mt-1 text-sm text-muted">{q.live_provider_results.label}</p>
          <dl className="mt-4 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">{rows(q.live_provider_results, ["label", "note"]).map(([k, v]) => (
            <div key={k} className="flex justify-between border-b border-line py-1.5"><dt className="text-muted">{k.replaceAll("_", " ")}</dt><dd className="font-semibold">{show(v)}</dd></div>))}</dl>
          <p className="mt-3 text-xs text-muted">{q.live_provider_results.note}</p></section>
      </>)}
    </div>
  );
}
