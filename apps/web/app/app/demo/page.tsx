"use client";
import Link from "next/link";
import { useState } from "react";
import { ErrorNote, PageTitle, Tag } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

type Result = { scenario: string; mission_id: string; status: string; revision?: number; stale_approval_replay_blocked?: boolean;
  refund_requests_on_intended_booking?: number; refund_requests_on_wrong_booking?: number; crm_tasks_created?: number; messages_sent_simulated?: number; environment: string };

const SCENARIOS = [
  { id: "a", title: "A. Consumer super-agent", text: "One request about a cancelled flight becomes one mission: refund, hotel date change, calendar fix, a draft message to family, and alternative flights read in parallel. A dependent message only runs after the refund is verified." },
  { id: "b", title: "B. Indian retail operator", text: "A customer at an electronics shop wants two keyboards for tomorrow. REDEEM disambiguates the customer by record, checks live stock, reserves atomically, updates the CRM stage and reads the reservation back." },
  { id: "d", title: "D. Browser operator (RESOLVE's signature mission)", text: "“Prepare a follow-up for Jordan Lee using the latest report, update the CRM and send it after I approve.” Two contacts share that name: REDEEM refuses to guess, picks the latest report by bytes, then drives a real Chromium through a simulated CRM and outbox. Snapshots before and after every action; verification reads the apps' APIs, not the page." },
  { id: "c", title: "C. Adversarial recovery", text: "The instruction changes (“wrong Rahul”), an old approval is replayed, and the provider loses its acknowledgement. REDEEM voids the stale approval, reconciles instead of resending, and proves exactly one effect." },
];

export default function Demo() {
  const [res, setRes] = useState<Record<string, Result>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = async (id: string) => {
    setBusy(id); setError(null);
    try { setRes((r) => ({ ...r, [id]: undefined as unknown as Result })); const out = await api<Result>(`/demo/scenarios/${id}/run`, { method: "POST" }); setRes((r) => ({ ...r, [id]: out })); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Scenario failed"); } finally { setBusy(null); }
  };
  const reset = async () => { try { await api("/demo/reset", { method: "POST" }); setRes({}); } catch (e) { setError(e instanceof ApiError ? e.message : "Reset failed"); } };
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageTitle title="Demo scenarios" sub="Repeatable runs of the real mission engine against seeded fixtures. Each run resets fixture data first; your own missions are kept." />
      <p className="rounded-xl bg-amber-soft p-4 text-sm"><Tag tone="amber">demo environment</Tag> <span className="ml-2">Fixture providers only. Your click on “Run scenario” stands in for the approval and is recorded as such. Nothing here contacts a real airline, shop or bank.</span></p>
      <ErrorNote error={error} />
      <ul className="space-y-4">{SCENARIOS.map((s) => {
        const r = res[s.id];
        return (<li key={s.id} className="card"><h2 className="text-lg font-bold">{s.title}</h2><p className="mt-1 text-sm text-muted">{s.text}</p>
          <div className="mt-3 flex flex-wrap items-center gap-3"><button className="btn-primary" disabled={busy !== null} onClick={() => void run(s.id)}>{busy === s.id ? "Running…" : "Run scenario"}</button>
            {r && <><Tag tone={r.status === "VERIFIED" ? "teal" : "amber"}>{r.status}</Tag><Link className="font-semibold text-indigo" href={`/app/missions/${r.mission_id}`}>Open mission, ledger and evidence</Link></>}</div>
          {r?.scenario === "d" && <p className="mt-3 text-sm">CRM tasks created (oracle): <strong>{r.crm_tasks_created}</strong>, messages committed, simulated delivery (oracle): <strong>{r.messages_sent_simulated}</strong></p>}
          {r?.scenario === "c" && <p className="mt-3 text-sm">Revision {r.revision}, stale approval replay blocked: <strong>{String(r.stale_approval_replay_blocked)}</strong>, refund requests on intended booking: <strong>{r.refund_requests_on_intended_booking}</strong>, on wrong booking: <strong>{r.refund_requests_on_wrong_booking}</strong></p>}
        </li>); })}</ul>
      <button className="btn-ghost" onClick={() => void reset()}>Reset fixture data</button>
    </div>
  );
}
