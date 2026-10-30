"use client";
import { useEffect, useState } from "react";
import { ErrorNote, PageTitle, Tag } from "@/components/ui";
import { api } from "@/lib/api";

type Q = { fixture_results: Record<string, unknown> & { label: string; language_breakdown: Record<string, { missions: number; verified: number }>; missions_by_status: Record<string, number> };
  live_provider_results: Record<string, unknown> & { label: string; note: string } };
const show = (v: unknown) => (v === null || v === undefined ? "Not measured" : typeof v === "object" ? JSON.stringify(v) : String(v));

export default function Quality() {
  const [q, setQ] = useState<Q | null>(null); const [error, setError] = useState<string | null>(null);
  useEffect(() => { api<Q>("/quality").then(setQ).catch((e) => setError(e.message)); }, []);
  const rows = (o: Record<string, unknown>, skip: string[]) => Object.entries(o).filter(([k]) => !skip.includes(k));
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageTitle title="Quality Lab" sub="Computed from this workspace’s real events. Anything REDEEM cannot measure says so." />
      <ErrorNote error={error} />
      {q && (<>
        <section className="card"><div className="flex flex-wrap items-center gap-2"><h2 className="text-lg font-bold">Mission reliability</h2><Tag tone="indigo">Local fixtures</Tag></div>
          <p className="mt-1 text-sm text-muted">{q.fixture_results.label}</p>
          <dl className="mt-4 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">{rows(q.fixture_results, ["label", "language_breakdown", "missions_by_status"]).map(([k, v]) => (
            <div key={k} className="flex justify-between border-b border-line py-1.5"><dt className="text-muted">{k.replaceAll("_", " ")}</dt><dd className="font-semibold">{show(v)}</dd></div>))}</dl>
          <h3 className="mt-5 font-semibold">By language detected</h3>
          <p className="text-sm text-muted">{Object.entries(q.fixture_results.language_breakdown).map(([l, v]) => `${l}: ${v.verified}/${v.missions} verified`).join(" · ") || "No missions yet"}</p></section>
        <section className="card"><div className="flex flex-wrap items-center gap-2"><h2 className="text-lg font-bold">Voice calls</h2><Tag tone="amber">Live provider</Tag></div>
          <p className="mt-1 text-sm text-muted">{q.live_provider_results.label}</p>
          <dl className="mt-4 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">{rows(q.live_provider_results, ["label", "note"]).map(([k, v]) => (
            <div key={k} className="flex justify-between border-b border-line py-1.5"><dt className="text-muted">{k.replaceAll("_", " ")}</dt><dd className="font-semibold">{show(v)}</dd></div>))}</dl>
          <p className="mt-3 text-xs text-muted">{q.live_provider_results.note}</p></section>
      </>)}
    </div>
  );
}
