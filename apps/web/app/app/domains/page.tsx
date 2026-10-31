"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ErrorNote, PageTitle, Tag } from "@/components/ui";
import { Tabs } from "@/components/viz";
import { api, ApiError } from "@/lib/api";

type RD = { id: string; label: string; counterparty: string; regulator: string; is_dispute: boolean; intake_fields: { key: string; example: string; critical: boolean }[]; issue_types: string[]; evidence_checklist: { id: string; label: string }[];
  escalation: { order: number; stage: string; text: string; links: string[] }[]; research_questions: string[]; corpus: Record<string, number>; corpus_note: string; my_cases: number; filing_channel: string; status: string };
type D = { id: string; name: string; description: string; status: string; backing: string; write_capabilities: string[]; read_capabilities: string[]; required_providers: string[]; approval_policy: string; notes: string };
type Scan = { risk_level: string; indicators: { code: string; severity: string; message: string }[]; disclaimer: string };
const EX: Record<string, string> = { travel: "My IndiGo flight 6E-2134 on 15 January 2026 was cancelled and they refused a refund of Rs 8,500. PNR: ABC123", banking: "Rs 12,500 was debited on 2026-01-15 from my HDFC Bank account without my consent. UTR 123456789012.",
  insurance: "Star Health rejected my claim of Rs 3,50,000 for surgery at Apollo Hospitals, citing a pre-existing condition. Policy number STAR/123456", telecom: "My Jio postpaid bill shows Rs 1,299 of extra charges I never used. Complaint no: CMP-8812 got no resolution.",
  ecommerce: "Flipkart refused to take back my damaged phone. Order ID OD123456789012 for Rs 18,999, the return was refused.", housing: "My landlord is refusing to return my security deposit of Rs 50,000 after I vacated on 1 February 2026.",
  government: "My passport application is pending for 4 months with no update from the department. Application number: PSP12345", healthcare: "Apollo Hospital charged me Rs 25,000 twice on the final bill dated 10 February 2026, an overcharged invoice." };

export default function Domains() {
  const router = useRouter();
  const [tab, setTab] = useState("rights");
  const [rd, setRd] = useState<RD[]>([]); const [items, setItems] = useState<D[]>([]); const [q, setQ] = useState(""); const [open, setOpen] = useState<string | null>(null);
  const [browser, setBrowser] = useState<{ cloud_browser: string; reason: string; fixture_browser: string; fixture_reason: string; isolation: string } | null>(null);
  const [error, setError] = useState<string | null>(null); const [text, setText] = useState(""); const [scan, setScan] = useState<Scan | null>(null);
  useEffect(() => {
    api<{ items: RD[] }>("/reclaim/domains").then((r) => setRd(r.items)).catch((e) => setError(e.message));
    api<{ items: D[] }>("/domains").then((r) => setItems(r.items)).catch(() => undefined);
    api<typeof browser>("/browser/status").then(setBrowser).catch(() => undefined);
  }, []);
  const start = async (d: RD) => { try { const c = await api<{ id: string }>("/cases", { body: { text: EX[d.id], domain: d.id } }); router.push(`/app/cases/${c.id}`); } catch (e) { setError(e instanceof ApiError ? e.message : "Could not start"); } };
  const run = async () => { try { setScan(await api<Scan>("/safety/scan", { body: { text } })); } catch (e) { setError(e instanceof ApiError ? e.message : "Scan failed"); } };
  const ql = q.toLowerCase();
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageTitle title="Domain Explorer" sub="Every domain's real intake, evidence checklist, escalation path and knowledge coverage, generated from the workflow definitions — not static cards." />
      <ErrorNote error={error} />
      <Tabs value={tab} onChange={setTab} tabs={[{ id: "rights", label: "Consumer-rights domains", count: rd.length }, { id: "mission", label: "Mission domains", count: items.length }, { id: "safety", label: "Payment safety" }]} />
      <div><label className="sr-only" htmlFor="dq">Search domains</label><input id="dq" className="input max-w-sm" placeholder="Search domains, fields, regulators…" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      {tab === "rights" && <ul className="grid gap-4 md:grid-cols-2">{rd.filter((d) => !ql || JSON.stringify(d).toLowerCase().includes(ql)).map((d) => (
        <li key={d.id} className="card"><div className="flex flex-wrap items-start justify-between gap-2"><h2 className="text-lg font-bold">{d.label}</h2><div className="flex gap-2"><Tag tone="teal">{d.status.replaceAll("_", " ").toLowerCase()}</Tag>{d.my_cases > 0 && <Tag tone="indigo">{d.my_cases} of your cases</Tag>}</div></div>
          <p className="mt-1 text-sm text-muted">{d.is_dispute ? `Counterparty: ${d.counterparty}, Regulator: ${d.regulator}` : "Administrative support only — never clinical advice."}</p>
          <dl className="mt-3 space-y-1.5 text-sm"><div><dt className="inline font-semibold">Needs: </dt><dd className="inline">{d.intake_fields.filter((f) => f.critical).map((f) => f.key.replaceAll("_", " ")).join(", ") || "issue description"}</dd></div>
            <div><dt className="inline font-semibold">Evidence checked: </dt><dd className="inline">{d.evidence_checklist.map((e) => e.label.split(" (")[0]).join(", ")}</dd></div>
            <div><dt className="inline font-semibold">Knowledge: </dt><dd className="inline">{Object.entries(d.corpus).map(([k, n]) => `${n} ${k.replaceAll("_", " ")}`).join(", ")}</dd></div>
            <div><dt className="inline font-semibold">Filing: </dt><dd className="inline text-muted">{d.filing_channel}</dd></div></dl>
          <button className="mt-3 text-sm font-semibold text-indigo underline" aria-expanded={open === d.id} onClick={() => setOpen(open === d.id ? null : d.id)}>{open === d.id ? "Hide workflow" : "Show workflow"}</button>
          {open === d.id && <div className="mt-3 space-y-3 rounded-xl bg-soft p-4 text-sm"><p className="text-xs text-muted">{d.corpus_note}</p>
            <div><p className="font-semibold">Intake fields</p><ul className="mt-1 grid gap-1 sm:grid-cols-2">{d.intake_fields.map((f) => <li key={f.key} className="text-xs"><strong>{f.key.replaceAll("_", " ")}</strong>{f.critical && " (required)"} — <span className="text-muted">{f.example}</span></li>)}</ul></div>
            <div><p className="font-semibold">Escalation ladder</p><ol className="mt-1 list-decimal space-y-1 pl-5 text-xs">{d.escalation.map((s) => <li key={s.order}>{s.text}</li>)}</ol></div>
            <div><p className="font-semibold">Questions the analysis answers</p><ul className="mt-1 list-disc pl-5 text-xs">{d.research_questions.map((r) => <li key={r}>{r}</li>)}</ul></div></div>}
          <button className="btn-primary mt-4" onClick={() => void start(d)}>Start with an example case</button></li>))}</ul>}
      {tab === "mission" && (<>
        {browser && <p className="rounded-xl bg-soft p-4 text-sm"><Tag tone={browser.fixture_browser === "AVAILABLE" ? "teal" : "amber"}>Fixture browser: {browser.fixture_browser}</Tag> <Tag tone="amber">Real-web browser: {browser.cloud_browser}</Tag><span className="mt-2 block text-muted">{browser.fixture_reason} {browser.reason} {browser.isolation}</span></p>}
        <ul className="grid gap-4 md:grid-cols-2">{items.filter((d) => !ql || JSON.stringify(d).toLowerCase().includes(ql)).map((d) => (<li key={d.id} className="card"><div className="flex items-start justify-between gap-2"><h2 className="font-bold">{d.name}</h2><Tag tone={d.status === "LOCALLY_TESTED" ? "teal" : "soft"}>{d.status.replaceAll("_", " ").toLowerCase()}</Tag></div>
          <p className="mt-1 text-sm text-muted">{d.description}</p><dl className="mt-3 space-y-1 text-sm"><div><dt className="inline font-semibold">Backing: </dt><dd className="inline">{d.backing === "fixture" ? "Local fixture (no real provider)" : "None"}</dd></div>
            <div><dt className="inline font-semibold">Operations: </dt><dd className="inline">{[...d.read_capabilities, ...d.write_capabilities].join(", ") || "—"}</dd></div><div><dt className="inline font-semibold">Approval: </dt><dd className="inline">{d.approval_policy}</dd></div></dl>{d.notes && <p className="mt-2 text-xs text-muted">{d.notes}</p>}</li>))}</ul></>)}
      {tab === "safety" && (<section className="card"><h2 className="text-lg font-bold">Payment-safety check</h2><p className="mt-1 text-sm text-muted">Rule-based indicators, not a fraud guarantee. REDEEM never asks for OTPs and never moves money.</p>
        <label htmlFor="scan" className="sr-only">Message to check</label><textarea id="scan" className="input mt-3 py-3" rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste the message…" /><button className="btn-primary mt-3" disabled={!text.trim()} onClick={() => void run()}>Check message</button>
        {scan && <div className="mt-4" role="status"><Tag tone={scan.risk_level === "high" ? "danger" : scan.risk_level === "medium" ? "amber" : "soft"}>Risk: {scan.risk_level.replaceAll("_", " ")}</Tag><ul className="mt-2 list-disc space-y-1 pl-5 text-sm">{scan.indicators.map((i) => <li key={i.code}><strong>{i.code.replaceAll("_", " ")}</strong> — {i.message}</li>)}</ul><p className="mt-2 text-xs text-muted">{scan.disclaimer}</p></div>}</section>)}
    </div>
  );
}
