"use client";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, PageTitle, Tag } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

type C = { provider: string; kind: string; scopes: string[]; status: string; revoked_at: string | null; note: string };
export default function Connections() {
  const [items, setItems] = useState<C[]>([]);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => api<{ items: C[] }>("/connectors").then((r) => setItems(r.items)).catch((e) => setError(e.message)), []);
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
    </div>
  );
}
