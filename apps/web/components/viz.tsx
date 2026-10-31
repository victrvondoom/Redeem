"use client";
import { useMemo, useState, type ReactNode } from "react";
import { Icon } from "./Icons";

export function Stat({ label, value, sub, tone = "ink", href }: { label: string; value: ReactNode; sub?: string; tone?: "ink" | "teal" | "amber" | "danger" | "indigo"; href?: string }) {
  const c = { ink: "text-ink", teal: "text-teal", amber: "text-ink", danger: "text-danger", indigo: "text-indigo" }[tone];
  const body = (<div className="card p-4"><p className="text-xs font-semibold uppercase tracking-wide text-muted">{label}</p><p className={`mt-1 text-3xl font-extrabold tabular-nums ${c}`}>{value}</p>{sub && <p className="mt-1 text-xs text-muted">{sub}</p>}</div>);
  return href ? <a href={href} className="block transition-transform hover:-translate-y-0.5">{body}</a> : body;
}

export function Meter({ value, max = 1, tone = "teal", label, showValue = true }: { value: number; max?: number; tone?: "teal" | "indigo" | "amber" | "danger"; label?: string; showValue?: boolean }) {
  const pct = Math.max(0, Math.min(100, (100 * value) / (max || 1)));
  const bg = { teal: "bg-teal", indigo: "bg-indigo", amber: "bg-amber", danger: "bg-danger" }[tone];
  return (
    <div className="flex items-center gap-2" role="meter" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-soft"><div className={`h-full ${bg} transition-all`} style={{ width: `${pct}%` }} /></div>
      {showValue && <span className="w-10 text-right text-xs tabular-nums text-muted">{Math.round(pct)}%</span>}
    </div>
  );
}

export function Tabs({ tabs, value, onChange }: { tabs: { id: string; label: string; count?: number }[]; value: string; onChange: (id: string) => void }) {
  return (
    <div role="tablist" className="flex gap-1 overflow-x-auto border-b border-line">
      {tabs.map((t) => (
        <button key={t.id} role="tab" aria-selected={value === t.id} onClick={() => onChange(t.id)}
          className={`-mb-px flex min-h-[44px] shrink-0 items-center gap-2 border-b-2 px-4 text-sm font-semibold ${value === t.id ? "border-indigo text-indigo" : "border-transparent text-muted hover:text-ink"}`}>
          {t.label}{t.count !== undefined && <span className="rounded-full bg-soft px-2 py-0.5 text-xs">{t.count}</span>}
        </button>))}
    </div>
  );
}

const STAGE_LABEL: Record<string, string> = { INTAKE: "Intake", CLASSIFIED: "Classify", ENTITIES_EXTRACTED: "Extract", NEEDS_INFO: "Needs info", EVIDENCE_COLLECTED: "Evidence", SOURCES_RETRIEVED: "Sources",
  EVIDENCE_SCORED: "Score", ANALYZED: "Analyze", DRAFTED: "Draft", ACTIONS_RANKED: "Rank", AWAITING_APPROVAL: "Approval", APPROVED: "Approved", SUBMITTED: "Submit", TRACKING: "Track",
  OUTCOME_VERIFIED: "Verified", OUTCOME_REPORTED_UNVERIFIED: "Reported", CLOSED: "Closed" };

export function Stepper({ stages, current, reached }: { stages: string[]; current: string; reached: string[] }) {
  const hidden = new Set(["NEEDS_INFO", "OUTCOME_REPORTED_UNVERIFIED"]);
  const shown = stages.filter((s) => !hidden.has(s) || reached.includes(s));
  const final = shown.filter((s) => !(s === "OUTCOME_VERIFIED" && reached.includes("OUTCOME_REPORTED_UNVERIFIED")));
  return (
    <ol className="flex gap-1 overflow-x-auto pb-1" aria-label="Case stages">
      {final.map((s) => {
        const done = reached.includes(s), cur = s === current;
        return (
          <li key={s} aria-current={cur ? "step" : undefined} className={`flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold ${cur ? "bg-indigo text-white" : done ? "bg-teal-soft text-teal" : "bg-soft text-muted"}`}>
            {done && !cur && <Icon name="check" size={12} />}{STAGE_LABEL[s] ?? s}
          </li>);
      })}
    </ol>
  );
}

export type TaskNode = { id: string; kind: string; owner: string; mode: string; depends_on: string[]; status: string; revision: number; attempts: number; retry_budget: number; error: string | null; output: Record<string, unknown> };
const T_TONE: Record<string, string> = { DONE: "#087F75", RUNNING: "#3448A5", FAILED: "#B72D2D", SKIPPED: "#8A949C", BLOCKED: "#EFA34A", CANCELLED: "#B8BEC4", QUEUED: "#64717C" };

/** Layered left-to-right rendering of the persisted task DAG (levels = longest dependency chain). */
export function Dag({ tasks, onSelect, selected }: { tasks: TaskNode[]; onSelect?: (t: TaskNode) => void; selected?: string }) {
  const rev = Math.max(0, ...tasks.map((t) => t.revision));
  const nodes = tasks.filter((t) => t.revision === rev);
  const layout = useMemo(() => {
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const level = new Map<string, number>();
    const lv = (n: TaskNode): number => { if (level.has(n.id)) return level.get(n.id)!; level.set(n.id, 0); const l = n.depends_on.map((d) => byId.get(d)).filter(Boolean).reduce((m, d) => Math.max(m, lv(d!) + 1), 0); level.set(n.id, l); return l; };
    nodes.forEach(lv);
    const cols: TaskNode[][] = [];
    nodes.forEach((n) => { const l = level.get(n.id)!; (cols[l] ??= []).push(n); });
    const pos = new Map<string, { x: number; y: number }>();
    cols.forEach((c, i) => c.forEach((n, j) => pos.set(n.id, { x: 20 + i * 190, y: 14 + j * 58 })));
    return { cols, pos, w: Math.max(1, cols.length) * 190 + 30, h: Math.max(1, ...cols.map((c) => c.length)) * 58 + 24 };
  }, [nodes]);
  if (!nodes.length) return null;
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface p-2">
      <svg width={layout.w} height={layout.h} role="img" aria-label="Task dependency graph" className="min-w-full">
        <defs><marker id="arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L8 4L0 8z" fill="#8A949C" /></marker></defs>
        {nodes.flatMap((n) => n.depends_on.map((d) => { const a = layout.pos.get(d), b = layout.pos.get(n.id); if (!a || !b) return null;
          return <path key={`${d}-${n.id}`} d={`M${a.x + 160} ${a.y + 20} C ${a.x + 180} ${a.y + 20}, ${b.x - 20} ${b.y + 20}, ${b.x} ${b.y + 20}`} fill="none" stroke="#8A949C" strokeWidth="1.2" markerEnd="url(#arr)" opacity="0.6" />; }))}
        {nodes.map((n) => { const p = layout.pos.get(n.id)!; const col = T_TONE[n.status] ?? "#64717C";
          return (
            <g key={n.id} transform={`translate(${p.x},${p.y})`} tabIndex={0} role="button" aria-label={`${n.kind} ${n.status}`} onClick={() => onSelect?.(n)} onKeyDown={(e) => e.key === "Enter" && onSelect?.(n)} style={{ cursor: "pointer" }}>
              <rect width="160" height="40" rx="10" fill="rgb(var(--surface))" stroke={selected === n.id ? "#3448A5" : col} strokeWidth={selected === n.id ? 2.5 : 1.6} />
              <rect width="5" height="40" rx="2.5" fill={col} />
              <text x="14" y="16" fontSize="11" fontWeight="700" fill="rgb(var(--ink))">{n.kind.length > 22 ? n.kind.slice(0, 21) + "…" : n.kind}</text>
              <text x="14" y="31" fontSize="10" fill="rgb(var(--muted))">{n.owner} · {n.status.toLowerCase()}{n.mode === "write" ? " · write" : ""}</text>
            </g>); })}
      </svg>
    </div>
  );
}

export function Collapsible({ title, children, defaultOpen = false, badge }: { title: string; children: ReactNode; defaultOpen?: boolean; badge?: ReactNode }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="card p-0">
      <button className="flex min-h-[52px] w-full items-center justify-between gap-3 px-5 text-left" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="flex items-center gap-2 text-lg font-bold">{title}{badge}</span><span aria-hidden className="text-muted">{open ? "−" : "+"}</span></button>
      {open && <div className="border-t border-line p-5">{children}</div>}
    </section>
  );
}
