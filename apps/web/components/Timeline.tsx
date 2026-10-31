"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ErrorNote, Tag } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

type Item = { at: string; kind: string; title: string; detail: string; href: string; ref: string };
type Resp = { total: number; counts: Record<string, number>; items: Item[] };
const KINDS = ["", "mission", "case", "call", "document", "memory", "conversation", "activity"];
const TONE: Record<string, "teal" | "indigo" | "amber" | "soft"> = { mission: "indigo", case: "indigo", call: "teal", document: "soft", memory: "teal", conversation: "soft", activity: "soft" };

/** Everything you have done with REDEEM, newest first, from the database (missions, cases, calls, documents, memory, conversation, activity). */
export function TimelineTab() {
  const [d, setD] = useState<Resp | null>(null);
  const [kind, setKind] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const LIMIT = 25;
  useEffect(() => {
    const t = setTimeout(() => {
      const p = new URLSearchParams({ limit: String(LIMIT), offset: String(page * LIMIT) }); if (kind) p.set("kind", kind); if (q) p.set("q", q);
      api<Resp>(`/timeline?${p}`).then((r) => { setD(r); setError(null); }).catch((e) => setError(e instanceof ApiError ? e.message : "Could not load"));
    }, 200);
    return () => clearTimeout(t);
  }, [kind, q, page]);
  return (
    <div className="space-y-4">
      <ErrorNote error={error} />
      <div className="grid gap-3 sm:grid-cols-[1fr_200px]"><div><label className="label" htmlFor="tl-q">Search your history</label><input id="tl-q" className="input" value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} placeholder="refund, FA2041, window…" /></div>
        <div><label className="label" htmlFor="tl-k">Type</label><select id="tl-k" className="input" value={kind} onChange={(e) => { setKind(e.target.value); setPage(0); }}>{KINDS.map((k) => <option key={k} value={k}>{k ? `${k}${d?.counts[k] ? ` (${d.counts[k]})` : ""}` : "Everything"}</option>)}</select></div></div>
      {d && d.items.length === 0 && <div className="card text-center text-muted">Nothing here yet. Start a mission, teach a preference or upload a document and it appears.</div>}
      <ol className="relative space-y-2 border-l border-line pl-5" aria-label="History timeline">{d?.items.map((i) => (
        <li key={`${i.kind}-${i.ref}`} className="relative"><span className="absolute -left-[27px] top-4 h-2.5 w-2.5 rounded-full bg-teal shadow-[0_0_10px_rgb(var(--green))]" aria-hidden="true" />
          <Link href={i.href} className="card !p-3 flex flex-col gap-1 hover:no-underline sm:flex-row sm:items-center sm:justify-between"><span className="min-w-0"><span className="block truncate font-semibold">{i.title}</span><span className="text-xs text-muted">{new Date(i.at).toLocaleString()} · {i.detail}</span></span><Tag tone={TONE[i.kind] ?? "soft"}>{i.kind}</Tag></Link></li>))}</ol>
      {d && d.total > LIMIT && <div className="flex items-center justify-between"><button className="btn-ghost" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button><span className="text-sm text-muted">{page * LIMIT + 1}–{Math.min(d.total, (page + 1) * LIMIT)} of {d.total}</span><button className="btn-ghost" disabled={(page + 1) * LIMIT >= d.total} onClick={() => setPage(page + 1)}>Next</button></div>}
    </div>
  );
}
