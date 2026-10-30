"use client";
import { useEffect, useState } from "react";
import { ErrorNote, PageTitle, Tag } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

type D = { id: string; name: string; description: string; status: string; backing: string; write_capabilities: string[]; read_capabilities: string[]; required_providers: string[]; approval_policy: string; risk_classes: string[]; notes: string; last_verified: string | null };
type Scan = { risk_level: string; indicators: { code: string; severity: string; message: string }[]; disclaimer: string };

export default function Domains() {
  const [items, setItems] = useState<D[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [scan, setScan] = useState<Scan | null>(null);
  useEffect(() => { api<{ items: D[] }>("/domains").then((r) => setItems(r.items)).catch((e) => setError(e.message)); }, []);
  const run = async () => { try { setScan(await api<Scan>("/safety/scan", { body: { text } })); setError(null); } catch (e) { setError(e instanceof ApiError ? e.message : "Scan failed"); } };
  const tone = (s: string) => (s === "LOCALLY_TESTED" ? "teal" : s === "SPECIFIED" ? "indigo" : "soft");
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageTitle title="Domain Explorer" sub="What each domain can do today, and whether it is real, fixture-backed, or not built." />
      <ErrorNote error={error} />
      <ul className="grid gap-4 md:grid-cols-2">{items.map((d) => (
        <li key={d.id} className="card"><div className="flex items-start justify-between gap-2"><h2 className="font-bold">{d.name}</h2><Tag tone={tone(d.status) as "teal"}>{d.status.replaceAll("_", " ")}</Tag></div>
          <p className="mt-1 text-sm text-muted">{d.description}</p>
          <dl className="mt-3 space-y-1 text-sm">
            <div><dt className="inline font-semibold">Backing: </dt><dd className="inline">{d.backing === "fixture" ? "Local fixture (no real provider)" : d.backing === "provider" ? "Live provider" : "None"}</dd></div>
            <div><dt className="inline font-semibold">Operations: </dt><dd className="inline">{[...d.read_capabilities, ...d.write_capabilities].join(", ") || "—"}</dd></div>
            {d.required_providers.length > 0 && <div><dt className="inline font-semibold">Needs: </dt><dd className="inline">{d.required_providers.join(", ")}</dd></div>}
            <div><dt className="inline font-semibold">Approval: </dt><dd className="inline">{d.approval_policy}</dd></div>
            <div><dt className="inline font-semibold">Last verified: </dt><dd className="inline">{d.last_verified ?? "Automated tests in this repo (see FEATURE_MATRIX)"}</dd></div></dl>
          {d.notes && <p className="mt-2 text-xs text-muted">{d.notes}</p>}</li>))}</ul>
      <section className="card" aria-labelledby="sc-h"><h2 id="sc-h" className="text-lg font-bold">Payment-safety check</h2>
        <p className="mt-1 text-sm text-muted">Paste a suspicious message. This is a rule-based indicator scan, not a fraud guarantee. REDEEM never asks for OTPs and never moves money.</p>
        <label htmlFor="scan" className="sr-only">Message to check</label>
        <textarea id="scan" className="input mt-3 py-3" rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste the message or describe the request…" />
        <button className="btn-primary mt-3" disabled={!text.trim()} onClick={() => void run()}>Check message</button>
        {scan && (<div className="mt-4" role="status"><Tag tone={scan.risk_level === "high" ? "danger" : scan.risk_level === "medium" ? "amber" : "soft"}>Risk: {scan.risk_level.replaceAll("_", " ")}</Tag>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">{scan.indicators.map((i) => <li key={i.code}><strong>{i.code.replaceAll("_", " ")}</strong> — {i.message}</li>)}</ul>
          <p className="mt-2 text-xs text-muted">{scan.disclaimer}</p></div>)}</section>
    </div>
  );
}
