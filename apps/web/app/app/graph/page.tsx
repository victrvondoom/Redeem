"use client";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ErrorNote, PageTitle, Tag } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

type N = { id: string; kind: string; label: string; status?: string };
type E = { source: string; target: string; rel: string };
type G = { nodes: N[]; edges: E[]; note: string };
const COLOR: Record<string, string> = { user: "#ff7a1a", memory: "#34d366", mission: "#ffb070", case: "#9be8b4", call: "#7ad7a0", document: "#c9d6cd", entity: "#ffd2a8", domain: "#5fae7a" };
const HREF = (n: N) => n.id.startsWith("mis:") ? `/app/missions/${n.id.slice(4)}` : n.id.startsWith("case:") ? `/app/cases/${n.id.slice(5)}` : n.kind === "memory" ? "/app/memory" : n.kind === "document" ? "/app/vault" : n.kind === "call" ? "/app/voice" : null;

export default function Graph() {
  const [g, setG] = useState<G | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [hide, setHide] = useState<Set<string>>(new Set());
  const load = useCallback(async () => { try { setG(await api<G>("/graph")); } catch (e) { setError(e instanceof ApiError ? e.message : "Could not load graph"); } }, []);
  useEffect(() => { void load(); }, [load]);

  const W = 900, H = 560;
  const layout = useMemo(() => {
    if (!g) return { pos: {} as Record<string, { x: number; y: number }>, nodes: [] as N[] };
    const nodes = g.nodes.filter((n) => !hide.has(n.kind) || n.kind === "user");
    const pos: Record<string, { x: number; y: number }> = { me: { x: W / 2, y: H / 2 } };
    const rings: Record<string, number> = { memory: 0.55, call: 0.55, mission: 0.78, case: 0.95, document: 0.95, entity: 1.05, domain: 1.05 };
    const byKind: Record<string, N[]> = {};
    nodes.filter((n) => n.kind !== "user").forEach((n) => (byKind[n.kind] ??= []).push(n));
    const kinds = Object.keys(byKind);
    const total = nodes.length - 1 || 1;
    let seen = 0;
    for (const k of kinds) {
      byKind[k].forEach((n, i) => {
        const a = ((seen + i) / total) * Math.PI * 2 - Math.PI / 2;
        const r = (rings[k] ?? 0.9) * Math.min(W, H) * 0.42;
        pos[n.id] = { x: W / 2 + Math.cos(a) * r * 1.35, y: H / 2 + Math.sin(a) * r };
      });
      seen += byKind[k].length;
    }
    return { pos, nodes };
  }, [g, hide]);
  const kinds = [...new Set((g?.nodes ?? []).map((n) => n.kind))];
  const sn = g?.nodes.find((n) => n.id === sel);
  const rel = (g?.edges ?? []).filter((e) => e.source === sel || e.target === sel);

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageTitle title="Memory Graph" sub="How your preferences, calls, missions, cases, entities and documents connect. Derived live from your own records, never shared with another account." />
      <ErrorNote error={error} />
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Show node kinds">{kinds.filter((k) => k !== "user").map((k) => (
        <button key={k} aria-pressed={!hide.has(k)} onClick={() => setHide((h) => { const n = new Set(h); if (n.has(k)) n.delete(k); else n.add(k); return n; })}
          className={`badge min-h-[36px] ${hide.has(k) ? "bg-soft text-muted line-through" : "bg-soft text-ink"}`}><span className="h-2.5 w-2.5 rounded-full" style={{ background: COLOR[k] }} />{k}, {g?.nodes.filter((n) => n.kind === k).length}</button>))}
        <span className="ml-auto text-xs text-muted">{g ? `${g.nodes.length} nodes, ${g.edges.length} links` : "Loading…"}</span></div>
      <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
        <div className="card overflow-hidden !p-0"><svg role="img" aria-label="Memory graph" viewBox={`0 0 ${W} ${H}`} className="h-auto w-full">
          {(g?.edges ?? []).map((e, i) => { const a = layout.pos[e.source], b = layout.pos[e.target]; if (!a || !b) return null; const on = sel && (e.source === sel || e.target === sel);
            return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={on ? "#ff7a1a" : "#22342a"} strokeWidth={on ? 2 : 1} opacity={sel && !on ? 0.25 : 1} />; })}
          {layout.nodes.map((n) => { const p = layout.pos[n.id]; if (!p) return null; const on = sel === n.id; const big = n.kind === "user";
            return (<g key={n.id} transform={`translate(${p.x},${p.y})`} tabIndex={0} role="button" aria-label={`${n.kind}: ${n.label}`} onClick={() => setSel(n.id)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") setSel(n.id); }} className="cursor-pointer outline-none">
              <circle r={big ? 22 : on ? 13 : 9} fill={COLOR[n.kind] ?? "#aaa"} stroke={on ? "#fff" : "#04060588"} strokeWidth={2}  />
              <text y={big ? 38 : 24} textAnchor="middle" fontSize="11" fill="#cfe0d3">{n.label.length > 22 ? n.label.slice(0, 21) + "…" : n.label}</text></g>); })}
        </svg></div>
        <aside className="card" aria-live="polite"><h2 className="text-lg font-bold">{sn ? sn.label : "Select a node"}</h2>
          {sn ? (<><p className="mt-1 flex flex-wrap gap-2"><Tag tone="teal">{sn.kind}</Tag>{sn.status && <Tag tone="soft">{sn.status}</Tag>}</p>
            <ul className="mt-3 space-y-1 text-sm">{rel.map((e, i) => { const other = g!.nodes.find((n) => n.id === (e.source === sel ? e.target : e.source)); return <li key={i} className="rounded-lg bg-soft px-3 py-2"><span className="text-muted">{e.source === sel ? e.rel : `${e.rel} (from)`}</span>, <button className="font-semibold text-teal" onClick={() => setSel(other!.id)}>{other?.label}</button></li>; })}</ul>
            {HREF(sn) && <Link className="btn-ghost mt-3" href={HREF(sn)!}>Open</Link>}</>)
            : <p className="mt-2 text-sm text-muted">Click a node to see its links. Orange is you; green nodes are things you told REDEEM or it verified.</p>}</aside>
      </div>
    </div>
  );
}
