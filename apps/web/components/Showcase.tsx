"use client";
import { useEffect, useRef, useState } from "react";
import { CountUp } from "./Cinematic";
import { Icon } from "./Icons";

const LAYERS: [string, string, string][] = [
  ["1. Plan", "Five actions", "mission"], ["2. Approve", "Exact amount", "check"], ["3. Execute", "Provider replies", "bolt"], ["4. Verify", "Read-back", "vault"],
];

/** 3D exploded stack of the four mission stages; parallax follows the pointer, active layer cycles. */
export function HeroDeck() {
  const [on, setOn] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => { const t = setInterval(() => setOn((o) => (o + 1) % 4), 1800); return () => clearInterval(t); }, []);
  const move = (e: React.PointerEvent) => {
    const el = box.current; if (!el) return; const r = el.getBoundingClientRect();
    el.style.setProperty("--ry", `${(((e.clientX - r.left) / r.width - 0.5) * 24 - 22).toFixed(1)}deg`);
    el.style.setProperty("--rx", `${((0.5 - (e.clientY - r.top) / r.height) * 14 + 10).toFixed(1)}deg`);
  };
  return (
    <div className="scene relative mx-auto h-[420px] w-full max-w-[460px] sm:h-[480px]" onPointerMove={move}>
      <div ref={box} className="preserve float3d absolute inset-x-0 top-8 mx-auto h-[360px] w-[300px] sm:w-[340px]" style={{ ["--rx" as string]: "10deg", ["--ry" as string]: "-22deg" }}>
        {LAYERS.map(([k, t, ic], i) => {
          const active = i === on;
          return (
            <div key={k} className="absolute left-0 w-full rounded-2xl border p-4 transition-[transform,opacity,border-color] duration-700"
              style={{ top: i * 84, transform: `translateZ(${(3 - i) * 46 + (active ? 34 : 0)}px)`, borderColor: active ? "rgb(var(--accent))" : "rgb(var(--line))",
                background: active ? "rgb(var(--indigo-soft))" : "rgb(var(--surface))", boxShadow: "var(--elev-2)" }}>
              <div className="flex items-center gap-3">
                <span className="grid h-10 w-10 place-items-center rounded-xl" style={{ background: active ? "rgb(var(--accent))" : "rgb(var(--soft))", color: active ? "rgb(var(--on-accent))" : "rgb(var(--accent))" }}><Icon name={ic} size={20} /></span>
                <div className="min-w-0"><p className="text-sm font-semibold text-teal">{k}</p><p className="truncate text-sm text-muted">{t}</p></div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

type Stats = { verified_claims: number; ledger_events: number; missions: number; knowledge_passages: number; consumer_rights_domains: number; encryption: string };

/** Live counters from this deployment's own database (GET /public/stats). Shows an honest placeholder if the API is unreachable. */
export function LiveStats() {
  const [s, setS] = useState<Stats | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    let dead = false;
    const load = () => fetch("/api/v1/public/stats").then((r) => r.ok ? r.json() : Promise.reject()).then((j) => { if (!dead) { setS(j); setErr(false); } }).catch(() => { if (!dead) setErr(true); });
    load(); const t = setInterval(load, 10000); return () => { dead = true; clearInterval(t); };
  }, []);
  const items: [string, number | undefined][] = [["Verified outcomes", s?.verified_claims], ["Ledger events", s?.ledger_events], ["Missions run", s?.missions], ["Knowledge passages", s?.knowledge_passages], ["Consumer-rights domains", s?.consumer_rights_domains]];
  return (
    <div>
      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {items.map(([k, v]) => (<li key={k} className="card !p-4 text-center"><p className="text-3xl font-extrabold tabular-nums">{v === undefined ? "—" : <CountUp to={v} />}</p><p className="mt-1 text-sm text-muted">{k}</p></li>))}
      </ul>
      <p className="mt-3 text-center text-sm text-muted">{err ? "The API is unreachable, so counters are unavailable." : "Live counts from this deployment, demo data included."}</p>
    </div>
  );
}

const SCRIPT: [string, string][] = [
  ["CLASSIFIED", "flight_recovery"], ["PLAN_READY", "four actions"], ["APPROVED", "digest bound"], ["ACKED", "reply, not proof"], ["VERIFIED", "read back"], ["RECEIPT", "hash-chained"],
];

/** Looping illustration of one mission through the engine. It is a labelled simulation; the real run lives in the console. */
export function PipelineSim() {
  const [n, setN] = useState(0);
  useEffect(() => { const t = setInterval(() => setN((x) => (x + 1) % (SCRIPT.length + 3)), 1100); return () => clearInterval(t); }, []);
  const shown = SCRIPT.slice(0, Math.min(n, SCRIPT.length));
  const pct = Math.round((Math.min(n, SCRIPT.length) / SCRIPT.length) * 100);
  return (
    <div className="card overflow-hidden !p-0">
      <div className="flex items-center justify-between border-b border-line px-4 py-2.5 text-xs"><span className="font-semibold text-teal">Simulation loop</span><span className="text-muted">Illustrative loop</span></div>
      <div className="h-1 overflow-hidden bg-soft"><div className="h-1 w-full origin-left bg-accent transition-transform duration-700" style={{ transform: `scaleX(${pct / 100})` }} /></div>
      <ol className="min-h-[300px] space-y-1.5 p-4 font-mono text-[13px]" aria-live="off">
        {shown.map(([k, v]) => (<li key={k} className="ticker-in flex flex-wrap gap-x-3"><span className={k === "VERIFIED" || k === "RECEIPT" ? "font-bold text-teal" : "font-bold text-ink"}>{k}</span><span className="text-muted">{v}</span></li>))}
      </ol>
    </div>
  );
}
