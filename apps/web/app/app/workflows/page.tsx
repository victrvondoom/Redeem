"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ErrorNote, PageTitle, Tag } from "@/components/ui";
import { api, ApiError, type Mission } from "@/lib/api";

type W = { id: string; name: string; inputs: string[]; preconditions: string[]; credentials: string[]; verification: string; recovery: string };

export default function Workflows() {
  const router = useRouter();
  const [items, setItems] = useState<W[]>([]);
  const [vals, setVals] = useState<Record<string, Record<string, string>>>({});
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api<{ items: W[] }>("/workflows").then((r) => setItems(r.items)).catch((e) => setError(e.message)); }, []);
  const start = async (w: W) => {
    try { const r = await api<{ mission: Mission }>(`/workflows/${w.id}/start`, { body: { inputs: vals[w.id] ?? {} } }); router.push(`/app/missions/${r.mission.id}`); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Could not start workflow"); }
  };
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageTitle title="Workflows" sub="Reusable, typed entry points. Each starts an ordinary mission through the same engine, so approvals and verification still apply." />
      <ErrorNote error={error} />
      <ul className="grid gap-4 md:grid-cols-2">{items.map((w) => (
        <li key={w.id} className="card"><h2 className="font-bold">{w.name}</h2>
          <p className="mt-1 text-xs text-muted">Needs: {w.credentials.join(", ")}, Verified by: {w.verification}</p>
          <div className="mt-3 space-y-2">{w.inputs.map((k) => (<div key={k}><label className="label" htmlFor={`${w.id}-${k}`}>{k.replaceAll("_", " ")}</label>
            <input id={`${w.id}-${k}`} className="input" value={vals[w.id]?.[k] ?? ""} onChange={(e) => setVals((v) => ({ ...v, [w.id]: { ...v[w.id], [k]: e.target.value } }))} /></div>))}</div>
          <p className="mt-3 text-xs text-muted">Recovery: {w.recovery}</p>
          <div className="mt-3 flex items-center gap-2"><button className="btn-primary" onClick={() => void start(w)}>Start workflow</button><Tag tone="indigo">fixture-backed</Tag></div></li>))}</ul>
    </div>
  );
}
