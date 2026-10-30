"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Composer, takePending } from "@/components/Composer";
import { Empty, ErrorNote, PageTitle, StatusBadge } from "@/components/ui";
import { api, ApiError, type Mission } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { when } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

type Row = Pick<Mission, "id" | "status" | "intent" | "created_at" | "domains"> & { outcome_headline?: string };
const OPEN = ["NEEDS_APPROVAL", "DISCOVERING", "AUTHORIZED", "EXECUTING", "UNCERTAIN", "INTENT_CAPTURED", "CLASSIFIED"];

export default function Console() {
  const { t, lang } = useI18n();
  const { me } = useAuth();
  const router = useRouter();
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [funnel, setFunnel] = useState<Record<string, string | number | null> | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const pending = takePending();
    if (pending) {
      api<Mission>("/missions", { body: pending }).then((m) => router.replace(`/app/missions/${m.id}`))
        .catch((e) => setError(e instanceof ApiError ? e.message : "Could not start the saved request."));
    }
    api<Record<string, string | number | null>>("/analytics/funnel").then(setFunnel).catch(() => undefined);
    api<{ items: Row[] }>("/missions?limit=20").then((r) => setRows(r.items)).catch((e) => setError(String(e.message ?? e)));
  }, [router]);

  const open = rows?.filter((r) => OPEN.includes(r.status)) ?? [];
  const recent = rows?.filter((r) => !OPEN.includes(r.status)) ?? [];
  const list = (items: Row[]) => (
    <ul className="space-y-2">{items.map((r) => (
      <li key={r.id}><Link href={`/app/missions/${r.id}`} className="card flex flex-col gap-2 p-4 hover:border-indigo sm:flex-row sm:items-center sm:justify-between">
        <span className="min-w-0"><span className="block truncate font-semibold">{r.intent}</span><span className="text-xs text-muted">{when(r.created_at, lang)} · {r.domains.join(", ") || "unclassified"}</span></span>
        <StatusBadge status={r.status} /></Link></li>))}</ul>);

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <PageTitle title={`${t("console.hello")}, ${me?.name.split(" ")[0] ?? ""}`} sub="Describe a problem. REDEEM plans it, asks before acting, then verifies the result." />
      <Composer compact />
      <ErrorNote error={error} />
      {funnel && !funnel.first_verified_outcome_at && (
        <section className="card" aria-labelledby="start-h"><h2 id="start-h" className="text-lg font-bold">Your first verified outcome</h2>
          <ol className="mt-3 space-y-2 text-sm">{[["Describe a problem", funnel.first_mission_at], ["Review the plan and approve", funnel.first_approval_at], ["See the verified receipt", funnel.first_verified_outcome_at]].map(([label, done]) => (
            <li key={String(label)} className="flex items-center gap-3"><span aria-hidden className={`grid h-6 w-6 place-items-center rounded-full text-xs font-bold ${done ? "bg-teal-soft text-teal" : "bg-soft text-muted"}`}>{done ? "✓" : "·"}</span>{String(label)}</li>))}</ol>
          <p className="mt-3 text-sm text-muted">No sample data yet? Try <Link className="font-semibold text-indigo" href="/app/demo">a demo scenario</Link> — it uses fixtures and says so.</p></section>)}
      <section aria-labelledby="active-h"><h2 id="active-h" className="mb-3 text-lg font-bold">{t("console.active")}</h2>
        {rows === null ? <p className="text-muted" role="status">Loading…</p> : open.length ? list(open) : <Empty title={t("console.empty")} />}</section>
      {recent.length > 0 && <section><h2 className="mb-3 text-lg font-bold">{t("console.recent")}</h2>{list(recent.slice(0, 6))}</section>}
    </div>
  );
}
