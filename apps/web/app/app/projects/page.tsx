"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Empty, ErrorNote, PageTitle, Tag } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

type P = { id: string; name: string; description: string; items: number; updated_at: string };
type Item = { id: string; kind: "mission" | "case" | "document"; ref_id: string; title?: string; status?: string | null; href?: string; missing: boolean };
type Detail = { id: string; name: string; description: string; items: Item[] };
type Pick = { kind: Item["kind"]; id: string; label: string };

export default function Projects() {
  const [list, setList] = useState<P[]>([]);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<Detail | null>(null);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [picks, setPicks] = useState<Pick[]>([]);
  const [add, setAdd] = useState("");
  const [error, setError] = useState<string | null>(null);
  const fail = (e: unknown, m: string) => setError(e instanceof ApiError ? e.message : m);

  const load = useCallback(async () => { try { setList((await api<{ items: P[] }>(`/projects${q ? `?q=${encodeURIComponent(q)}` : ""}`)).items); } catch (e) { fail(e, "Could not load projects"); } }, [q]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    Promise.all([
      api<{ items: { id: string; intent: string }[] }>("/missions").catch(() => ({ items: [] })),
      api<{ items: { id: string; title: string }[] }>("/cases?limit=100").catch(() => ({ items: [] })),
      api<{ items: { id: string; filename: string }[] }>("/documents?limit=200").catch(() => ({ items: [] })),
    ]).then(([m, c, d]) => setPicks([
      ...(m.items ?? []).map((x) => ({ kind: "mission" as const, id: x.id, label: `Mission: ${x.intent.slice(0, 70)}` })),
      ...(c.items ?? []).map((x) => ({ kind: "case" as const, id: x.id, label: `Case: ${x.title.slice(0, 70)}` })),
      ...(d.items ?? []).map((x) => ({ kind: "document" as const, id: x.id, label: `Document: ${x.filename}` })),
    ]));
  }, []);
  const open = async (id: string) => { try { setSel(await api<Detail>(`/projects/${id}`)); } catch (e) { fail(e, "Could not open project"); } };
  const create = async () => { try { const p = await api<Detail>("/projects", { method: "POST", body: { name, description: desc } }); setName(""); setDesc(""); await load(); await open(p.id); } catch (e) { fail(e, "Could not create"); } };
  const attach = async () => { const p = picks.find((x) => `${x.kind}:${x.id}` === add); if (!sel || !p) return; try { await api(`/projects/${sel.id}/items`, { method: "POST", body: { kind: p.kind, ref_id: p.id } }); setAdd(""); await open(sel.id); await load(); } catch (e) { fail(e, "Could not add"); } };
  const detach = async (it: Item) => { if (!sel) return; try { await api(`/projects/${sel.id}/items/${it.id}`, { method: "DELETE" }); await open(sel.id); await load(); } catch (e) { fail(e, "Could not remove"); } };
  const del = async () => { if (!sel) return; try { await api(`/projects/${sel.id}`, { method: "DELETE" }); setSel(null); await load(); } catch (e) { fail(e, "Could not delete"); } };

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageTitle title="Projects" sub="Group the missions, cases and documents that belong to one problem, so everything about it is in one place." />
      <ErrorNote error={error} />
      <div className="grid gap-6 md:grid-cols-[320px_1fr]">
        <aside className="space-y-4">
          <section className="card space-y-2" aria-labelledby="new-h">
            <h2 id="new-h" className="font-bold">New project</h2>
            <label className="block text-sm font-semibold">Name<input className="input mt-1 w-full" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} /></label>
            <label className="block text-sm font-semibold">Description<textarea className="input mt-1 w-full" value={desc} onChange={(e) => setDesc(e.target.value)} maxLength={2000} /></label>
            <button className="btn-primary" disabled={!name.trim()} onClick={create}>Create</button>
          </section>
          <label className="block text-sm font-semibold">Search<input className="input mt-1 w-full" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Project name" /></label>
          {list.length === 0 ? <Empty title={q ? "No match" : "No projects yet"} /> : (
            <ul className="space-y-2">{list.map((p) => (<li key={p.id}><button onClick={() => open(p.id)} className={`card w-full !p-3 text-left ${sel?.id === p.id ? "ring-2 ring-accent" : ""}`}><span className="block font-semibold">{p.name}</span><span className="text-xs text-muted">{p.items} item{p.items === 1 ? "" : "s"}</span></button></li>))}</ul>)}
        </aside>
        <section aria-live="polite">
          {!sel ? <Empty title="Pick a project">Or create one on the left.</Empty> : (
            <div className="card space-y-4">
              <div className="flex flex-wrap items-start justify-between gap-2"><div><h2 className="text-xl font-bold">{sel.name}</h2>{sel.description && <p className="mt-1 text-sm text-muted">{sel.description}</p>}</div><button className="btn-ghost" onClick={del}>Delete project</button></div>
              <div className="flex flex-wrap gap-2"><select className="input min-w-0 flex-1" value={add} onChange={(e) => setAdd(e.target.value)} aria-label="Add an item"><option value="">Add a mission, case or document…</option>{picks.map((p) => <option key={`${p.kind}:${p.id}`} value={`${p.kind}:${p.id}`}>{p.label}</option>)}</select><button className="btn-primary" disabled={!add} onClick={attach}>Add</button></div>
              {sel.items.length === 0 ? <p className="text-sm text-muted">Nothing in this project yet.</p> : (
                <ul className="divide-y divide-line">{sel.items.map((it) => (
                  <li key={it.id} className="flex items-center justify-between gap-3 py-2">
                    <div className="min-w-0"><Tag tone="soft">{it.kind}</Tag> {it.missing ? <span className="text-sm text-muted">deleted {it.kind}</span> : <Link className="text-sm font-semibold" href={it.href ?? "#"}>{it.title}</Link>}{it.status && <span className="ml-2 text-xs text-muted">{it.status.toLowerCase()}</span>}</div>
                    <button className="btn-ghost !px-3 !py-1 text-xs" onClick={() => detach(it)}>Remove</button>
                  </li>))}</ul>)}
            </div>)}
        </section>
      </div>
    </div>
  );
}
