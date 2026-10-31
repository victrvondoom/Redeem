"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Composer, takePending } from "@/components/Composer";
import { Icon } from "@/components/Icons";
import { Empty, ErrorNote, PageTitle, StatusBadge, Tag } from "@/components/ui";
import { Stat } from "@/components/viz";
import { api, ApiError, type Mission } from "@/lib/api";
import { when } from "@/lib/format";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import type { Overview } from "@/lib/types";

type Row = Pick<Mission, "id" | "status" | "intent" | "created_at" | "domains"> & { outcome_headline?: string };
const ICON: Record<string, string> = { approval: "check", question: "alert", uncertain: "alert", paused: "clock", escalated: "shield", case_info: "cases", case_approval: "cases", overdue: "clock" };
const TONE: Record<string, "amber" | "indigo" | "danger"> = { approval: "amber", question: "indigo", uncertain: "danger", paused: "amber", escalated: "danger", case_info: "indigo", case_approval: "amber", overdue: "danger" };
const SAY: Record<string, string> = { VERIFIED: "verified an effect", VERIFICATION_FAILED: "verification failed", APPROVED: "approval recorded", ACK_LOST: "lost acknowledgement (reconciling)", RECONCILED_FOUND: "found the existing effect", RECEIPT: "receipt issued",
  USER_ACTION_REQUIRED: "paused for a user-only step", APPROVAL_INVALIDATED: "an approval was voided", HUMAN_ESCALATION: "flagged for a human", REVISION_CREATED: "instruction revised", CASE_CREATED: "case opened",
  DOCUMENT_ATTACHED: "document attached", DRAFT_EDITED: "draft edited", PROVIDER_UPDATE: "provider update logged" };

export default function CommandCenter() {
  const { t, lang } = useI18n();
  const { me } = useAuth();
  const router = useRouter();
  const [ov, setOv] = useState<Overview | null>(null);
  const [rows, setRows] = useState<Row[] | null>(null);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("active");
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  const load = useCallback(async () => {
    try {
      const [o, m] = await Promise.all([api<Overview>("/overview"), api<{ items: Row[] }>(`/missions?limit=50${q ? `&q=${encodeURIComponent(q)}` : ""}`)]);
      setOv(o); setRows(m.items);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not load"); }
  }, [q]);

  useEffect(() => {
    if (!started.current) {
      started.current = true;
      const pending = takePending();
      if (pending) api<Mission>("/missions", { body: pending }).then((m) => router.replace(`/app/missions/${m.id}`)).catch((e) => setError(e instanceof ApiError ? e.message : "Could not start the saved request."));
    }
    void load();
    const h = setInterval(() => void load(), 5000);   // live: polls the persisted state
    return () => clearInterval(h);
  }, [load, router]);

  const OPEN = ["NEEDS_APPROVAL", "DISCOVERING", "AUTHORIZED", "EXECUTING", "UNCERTAIN", "INTENT_CAPTURED", "CLASSIFIED"];
  const shown = (rows ?? []).filter((r) => filter === "all" ? true : filter === "active" ? OPEN.includes(r.status) : filter === "done" ? ["VERIFIED", "PARTIALLY_VERIFIED"].includes(r.status) : ["FAILED", "CANCELLED"].includes(r.status));
  const c = ov?.counts;
  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <PageTitle title={`${t("console.hello")}, ${me?.name.split(" ")[0] ?? ""}`} sub="Mission Command Center — everything REDEEM is doing for you, and what needs you." />
      <ErrorNote error={error} />
      {ov && c && c.verified_outcomes === 0 && (
        <section className="card" aria-labelledby="start-h"><h2 id="start-h" className="text-lg font-bold">Your first verified outcome</h2>
          <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-muted"><li>Describe what you need below (voice or text).</li><li>Review the proposed plan and approve only the actions you want.</li><li>REDEEM runs them, re-checks the result independently, and shows a receipt.</li></ol></section>
      )}
      <section aria-label="Overview" className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-6">
        <Stat label="Active missions" value={c?.missions_active ?? "—"} tone="indigo" />
        <Stat label="Needs you" value={ov?.attention.length ?? "—"} tone={ov && ov.attention.length ? "amber" : "ink"} />
        <Stat label="Verified outcomes" value={c?.verified_outcomes ?? "—"} tone="teal" />
        <Stat label="Open cases" value={c ? c.cases_total - (c.cases_by_status.CLOSED ?? 0) - (c.cases_by_status.RESOLVED ?? 0) : "—"} href="/app/cases" />
        <Stat label="Evidence files" value={c?.documents ?? "—"} href="/app/vault" />
        <Stat label="Browser snapshots" value={c?.browser_snapshots ?? "—"} sub="before/after evidence" />
      </section>
      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-6">
          <Composer compact />
          <section aria-labelledby="ms-h">
            <div className="mb-3 flex flex-wrap items-end justify-between gap-3"><h2 id="ms-h" className="text-lg font-bold">{t("console.active")}</h2>
              <div className="flex flex-wrap items-center gap-2">
                <label className="sr-only" htmlFor="mq">Search missions</label>
                <input id="mq" className="input !min-h-[40px] w-44" placeholder="Search missions" value={q} onChange={(e) => setQ(e.target.value)} />
                {["active", "done", "stopped", "all"].map((f) => <button key={f} onClick={() => setFilter(f)} aria-pressed={filter === f} className={`badge min-h-[32px] ${filter === f ? "bg-deep text-white" : "bg-soft text-muted"}`}>{f}</button>)}
              </div></div>
            {rows === null ? <p className="text-muted" role="status">Loading…</p> : shown.length ? (
              <ul className="space-y-2">{shown.map((r) => (
                <li key={r.id}><Link href={`/app/missions/${r.id}`} className="card flex flex-col gap-2 p-4 hover:border-indigo sm:flex-row sm:items-center sm:justify-between">
                  <span className="min-w-0"><span className="block truncate font-semibold">{r.intent}</span><span className="text-xs text-muted">{when(r.created_at, lang)} · {r.domains.join(", ") || "unclassified"}</span></span><StatusBadge status={r.status} /></Link></li>))}</ul>
            ) : <Empty title={t("console.empty")}>Describe a problem above, open a case, or try a demo scenario.</Empty>}
          </section>
        </div>
        <div className="space-y-6">
          <section aria-labelledby="att-h" className="card"><h2 id="att-h" className="flex items-center gap-2 text-lg font-bold"><Icon name="alert" size={18} /> Needs your attention</h2>
            {ov && ov.attention.length ? <ul className="mt-3 space-y-2">{ov.attention.slice(0, 7).map((a, i) => (
              <li key={i}><Link href={a.href} className="flex gap-3 rounded-xl border border-line p-3 hover:border-indigo"><span className="mt-0.5 text-indigo"><Icon name={ICON[a.kind] ?? "alert"} size={16} /></span>
                <span className="min-w-0"><span className="flex items-center gap-2 text-sm font-semibold">{a.title} <Tag tone={TONE[a.kind] ?? "soft"}>{a.kind.replace("_", " ")}</Tag></span><span className="block truncate text-xs text-muted">{a.detail}</span></span></Link></li>))}</ul>
              : <p className="mt-3 text-sm text-muted">{ov ? "Nothing is waiting on you." : "Loading…"}</p>}
          </section>
          <section aria-labelledby="feed-h" className="card"><h2 id="feed-h" className="flex items-center gap-2 text-lg font-bold"><Icon name="bolt" size={18} /> Live activity</h2>
            {ov && ov.recent.length ? <ol className="mt-3 space-y-2 text-sm">{ov.recent.slice(0, 9).map((r, i) => (
              <li key={i}><Link href={r.href} className="flex items-start gap-3 hover:text-indigo"><span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-teal" aria-hidden /><span><span className="font-medium">{SAY[r.type] ?? r.type.toLowerCase().replaceAll("_", " ")}</span>
                <span className="block text-xs text-muted">{r.source} · {when(r.at, lang)}</span></span></Link></li>))}</ol> : <p className="mt-3 text-sm text-muted">Events appear here as work happens. Polls every 5 seconds.</p>}
          </section>
          <p className="text-xs text-muted">{ov?.scope}</p>
        </div>
      </div>
    </div>
  );
}
