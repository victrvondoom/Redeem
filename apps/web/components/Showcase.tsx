"use client";
import { useEffect, useRef, useState } from "react";
import { CountUp } from "./Cinematic";
import { Icon } from "./Icons";

const LAYERS: [string, string, string, string][] = [
  ["01 · PLAN", "Refund · hotel · calendar · family draft", "5 actions, each with a digest", "mission"],
  ["02 · APPROVE", "Bound to exact target + amount", "change anything → approval void", "check"],
  ["03 · EXECUTE", "Provider acknowledges", "ACK is not proof", "bolt"],
  ["04 · VERIFY", "Independent read-back", "DATABASE VERIFIED ✓", "vault"],
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
      <div aria-hidden="true" className="absolute left-1/2 top-1/2 h-72 w-72 -translate-x-1/2 -translate-y-1/2 rounded-full blur-3xl" style={{ background: "rgb(var(--accent) / 0.22)" }} />
      <div ref={box} className="preserve float3d absolute inset-x-0 top-8 mx-auto h-[360px] w-[300px] sm:w-[340px]" style={{ ["--rx" as string]: "10deg", ["--ry" as string]: "-22deg" }}>
        {LAYERS.map(([k, t, s, ic], i) => {
          const active = i === on;
          return (
            <div key={k} className="absolute left-0 w-full rounded-2xl border p-4 transition-all duration-700"
              style={{ top: i * 84, transform: `translateZ(${(3 - i) * 46 + (active ? 34 : 0)}px)`, borderColor: active ? "rgb(var(--accent))" : "rgb(var(--line))",
                background: active ? "linear-gradient(145deg, rgb(10 48 62 / .95), rgb(8 18 30 / .95))" : "linear-gradient(145deg, rgb(18 24 38 / .92), rgb(9 12 20 / .92))",
                boxShadow: active ? "0 0 50px rgb(var(--accent) / .45), 0 30px 50px -20px #000" : "0 24px 40px -20px #000", backdropFilter: "blur(8px)" }}>
              <div className="flex items-center gap-3">
                <span className="grid h-10 w-10 place-items-center rounded-xl" style={{ background: active ? "rgb(var(--accent))" : "rgb(var(--soft))", color: active ? "#03050A" : "rgb(var(--accent))" }}><Icon name={ic} size={20} /></span>
                <div className="min-w-0"><p className="text-[11px] font-bold tracking-[0.2em] text-teal">{k}</p><p className="truncate text-sm font-semibold">{t}</p><p className="truncate text-xs text-muted">{s}</p></div>
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
        {items.map(([k, v]) => (<li key={k} className="card !p-4 text-center"><p className="glow-text text-3xl font-extrabold tabular-nums">{v === undefined ? "—" : <CountUp to={v} />}</p><p className="mt-1 text-xs font-semibold uppercase tracking-wider text-muted">{k}</p></li>))}
      </ul>
      <p className="mt-3 flex items-center justify-center gap-2 text-xs text-muted"><span className="live-dot" aria-hidden="true" />{err ? "API unreachable — counters unavailable" : "Live from this deployment's database · includes demo fixtures · not a customer metric"}</p>
    </div>
  );
}

const SCRIPT: [string, string][] = [
  ["INTENT_CAPTURED", "“Flight FA2041 cancelled, I need my refund”"], ["CLASSIFIED", "flight_recovery · entity FA2041 bound"], ["READS_COMPLETED", "3 alternatives + booking read in parallel"],
  ["PLAN_READY", "refund · hotel · calendar · family draft"], ["APPROVED", "digest 9f3c…a1 bound to booking + amount"], ["DISPATCHING", "idempotency key issued"],
  ["ACKED", "provider acknowledged (not proof)"], ["VERIFIED", "refund_request found by independent read-back"], ["RECEIPT", "hash-chained, downloadable"],
];

/** Looping illustration of one mission through the engine. It is a labelled simulation; the real run lives in the console. */
export function PipelineSim() {
  const [n, setN] = useState(0);
  useEffect(() => { const t = setInterval(() => setN((x) => (x + 1) % (SCRIPT.length + 3)), 1100); return () => clearInterval(t); }, []);
  const shown = SCRIPT.slice(0, Math.min(n, SCRIPT.length));
  const pct = Math.round((Math.min(n, SCRIPT.length) / SCRIPT.length) * 100);
  return (
    <div className="card scanline overflow-hidden !p-0">
      <div className="flex items-center justify-between border-b border-line px-4 py-2.5 text-xs"><span className="flex items-center gap-2 font-bold tracking-widest text-teal"><span className="live-dot" aria-hidden="true" />ENGINE · SIMULATION LOOP</span><span className="text-muted">illustrative — real runs in console → Live</span></div>
      <div className="h-1 bg-soft"><div className="h-1 bg-teal transition-all duration-700" style={{ width: `${pct}%`, boxShadow: "0 0 12px rgb(var(--accent))" }} /></div>
      <ol className="min-h-[300px] space-y-1.5 p-4 font-mono text-[13px]" aria-live="off">
        {shown.map(([k, v], i) => (<li key={k} className="ticker-in flex flex-wrap gap-x-3"><span className="text-muted">{String(i + 1).padStart(2, "0")}</span><span className={k === "VERIFIED" || k === "RECEIPT" ? "font-bold text-teal" : "font-bold text-ink"}>{k}</span><span className="text-muted">{v}</span></li>))}
      </ol>
    </div>
  );
}
