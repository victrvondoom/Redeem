"use client";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, PageTitle, Tag } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

type H = { provider: string; condition: string; configured: boolean; healthy: boolean; detail: string };
type Mf = { provider: string; kind: string; auth: string; capabilities: string[]; retry: string; idempotency: string; verification: string; condition: string; notes: string };
type C = { provider: string; kind: string; scopes: string[]; status: string; revoked_at: string | null; note: string };
export default function Connections() {
  const [items, setItems] = useState<C[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<H[]>([]);
  const [mf, setMf] = useState<Mf[]>([]);
  const load = useCallback(async () => {
    try { setItems((await api<{ items: C[] }>("/connectors")).items); setHealth((await api<{ items: H[] }>("/connectors/health")).items); setMf((await api<{ items: Mf[] }>("/connectors/manifests")).items); }
    catch (e) { setError(e instanceof Error ? e.message : "Failed"); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const toggle = async (c: C) => { try { await api(`/connectors/${c.provider}/${c.status === "active" ? "revoke" : "reinstate"}`, { method: "POST" }); await load(); } catch (e) { setError(e instanceof ApiError ? e.message : "Failed"); } };
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageTitle title="Connections" sub="Every action runs through a connection you can revoke. Revoking stops all further actions on it immediately." />
      <ErrorNote error={error} />
      <ul className="space-y-3">{items.map((c) => (
        <li key={c.provider} className="card flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div><div className="flex flex-wrap items-center gap-2"><h2 className="font-bold">{c.provider.replaceAll("_", " ")}</h2><Tag tone={c.status === "active" ? "teal" : c.status === "revoked" ? "danger" : "amber"}>{c.status}</Tag><Tag>{c.kind}</Tag></div>
            <p className="mt-1 text-sm text-muted">Scopes: {c.scopes.join(", ")}</p>{c.note && <p className="text-xs text-muted">{c.note}</p>}</div>
          {c.kind === "fixture" && <button className="btn-ghost" onClick={() => void toggle(c)}>{c.status === "active" ? "Revoke" : "Reinstate"}</button>}
        </li>))}</ul>
      <section aria-labelledby="hl-h"><h2 id="hl-h" className="mb-2 text-lg font-bold">Connector health &amp; manifests</h2>
        <p className="mb-3 text-sm text-muted">Condition is one of UNCONFIGURED, FIXTURE_VERIFIED (tested against a local stand-in) or LIVE_VERIFIED (exercised against the real service). Nothing is LIVE_VERIFIED yet.</p>
        <ul className="space-y-2">{mf.map((m) => { const h = health.find((x) => x.provider === m.provider); return (
          <li key={m.provider} className="card p-4 text-sm"><div className="flex flex-wrap items-center gap-2"><strong>{m.provider.replaceAll("_", " ")}</strong><Tag tone={m.condition === "FIXTURE_VERIFIED" ? "indigo" : "amber"}>{m.condition}</Tag>
            {h && <Tag tone={h.healthy ? "teal" : "soft"}>{h.healthy ? "healthy" : h.detail}</Tag>}</div>
            <p className="mt-1 text-xs text-muted">Auth: {m.auth}, Can: {m.capabilities.join(", ")}, Verification: {m.verification}, Idempotency: {m.idempotency}, Retry: {m.retry}</p>{m.notes && <p className="text-xs text-muted">{m.notes}</p>}</li>); })}</ul></section>
    </div>
  );
}
