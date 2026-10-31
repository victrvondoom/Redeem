"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Empty, ErrorNote, PageTitle, Tag } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { when } from "@/lib/format";

type Doc = { id: string; name: string; sha256: string; size_bytes: number; created_at: number; operation: string; source_ids: string };

export default function Studio() {
  const [docs, setDocs] = useState<Doc[]>([]); const [sel, setSel] = useState<string[]>([]); const [error, setError] = useState<string | null>(null); const [notice, setNotice] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState(""); const [text, setText] = useState(""); const [pages, setPages] = useState(""); const [deg, setDeg] = useState("90"); const [preview, setPreview] = useState<{ name: string; text: string } | null>(null);
  const ref = useRef<HTMLInputElement>(null);
  const load = useCallback(async () => { try { setDocs((await api<{ items: Doc[] }>("/studio/documents")).items); } catch (e) { setError(e instanceof Error ? e.message : "Failed"); } }, []);
  useEffect(() => { void load(); }, [load]);
  const run = async (fn: () => Promise<unknown>, ok: string) => { setBusy(true); setError(null); setNotice(null); try { await fn(); setNotice(ok); await load(); } catch (e) { setError(e instanceof ApiError ? e.message : "Failed"); } finally { setBusy(false); } };
  const shaMap = Object.fromEntries(docs.filter((d) => sel.includes(d.id)).map((d) => [d.id, d.sha256]));
  const pageList = pages.split(",").map((p) => parseInt(p.trim(), 10)).filter((n) => !Number.isNaN(n));
  const tf = (operation: string) => run(() => api("/studio/transform", { body: { operation, document_ids: sel, expected_sha256: shaMap, degrees: operation === "rotate" ? Number(deg) : undefined, pages: pageList.length ? pageList : undefined } }), `${operation.replace("_", " ")} done; a new PDF was created and the source is unchanged.`);
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageTitle title="PDF Studio" sub="Rotate, remove pages, merge and create PDFs, inherited from RESOLVE. Every transform is bound to the exact source version you selected and produces a new file." />
      <ErrorNote error={error} />{notice && <p role="status" className="rounded-xl bg-teal-soft px-4 py-3 text-sm font-medium text-teal">{notice}</p>}
      <section className="card flex flex-wrap items-center justify-between gap-3"><p className="text-sm text-muted">Up to 20 MB per PDF. Encrypted PDFs are refused.</p>
        <div><input ref={ref} type="file" accept="application/pdf,.pdf" className="sr-only" aria-label="Import a PDF" onChange={(e) => { const f = e.target.files?.[0]; if (f) { const form = new FormData(); form.append("file", f); void run(() => api("/studio/import", { form }), `Imported ${f.name}.`); } e.target.value = ""; }} /><button className="btn-primary" disabled={busy} onClick={() => ref.current?.click()}>Import PDF</button></div></section>
      <section className="card" aria-labelledby="dl-h"><h2 id="dl-h" className="text-lg font-bold">Documents</h2>
        {docs.length === 0 ? <div className="mt-3"><Empty title="No PDFs yet">Import one, or create a report below.</Empty></div> : <ul className="mt-3 divide-y divide-line">{docs.map((d) => (<li key={d.id} className="flex flex-wrap items-center gap-3 py-3 text-sm">
          <label className="flex min-h-[44px] items-center gap-3"><input type="checkbox" className="h-5 w-5" checked={sel.includes(d.id)} onChange={(e) => setSel(e.target.checked ? [...sel, d.id] : sel.filter((x) => x !== d.id))} aria-label={`Select ${d.name}`} /><span className="font-semibold">{d.name}</span></label>
          <Tag>{d.operation}</Tag><span className="text-xs text-muted">{(d.size_bytes / 1024).toFixed(1)} KB · {when(new Date(d.created_at * 1000).toISOString())}</span>
          <span className="ml-auto flex gap-2"><button className="btn-ghost !min-h-[36px] px-3" onClick={() => void api<{ text: string }>(`/studio/documents/${d.id}/text`).then((r) => setPreview({ name: d.name, text: r.text })).catch((e) => setError(e.message))}>Text</button>
            <a className="btn-ghost !min-h-[36px] px-3" href={`/api/v1/studio/documents/${d.id}/download`}>Download</a>
            <button className="btn-ghost !min-h-[36px] px-3 text-danger" onClick={() => { if (confirm(`Delete ${d.name}?`)) void run(() => api(`/studio/documents/${d.id}`, { method: "DELETE" }), "Deleted."); }}>Delete</button></span></li>))}</ul>}
        {docs.length > 0 && (<div className="mt-4 rounded-xl bg-soft p-4"><p className="text-sm font-semibold">Transform the {sel.length} selected</p>
          <div className="mt-2 flex flex-wrap items-end gap-3"><div><label className="label" htmlFor="pg">Pages (comma separated, optional)</label><input id="pg" className="input w-48" placeholder="1,3" value={pages} onChange={(e) => setPages(e.target.value)} /></div>
            <div><label className="label" htmlFor="dg">Rotate by</label><select id="dg" className="input w-28" value={deg} onChange={(e) => setDeg(e.target.value)}>{["90", "180", "270"].map((d) => <option key={d} value={d}>{d}°</option>)}</select></div>
            <button className="btn-ghost" disabled={busy || sel.length !== 1} onClick={() => void tf("rotate")}>Rotate</button><button className="btn-ghost" disabled={busy || sel.length !== 1 || !pageList.length} onClick={() => void tf("delete_pages")}>Remove pages</button><button className="btn-ghost" disabled={busy || sel.length < 2} onClick={() => void tf("merge")}>Merge</button></div></div>)}
        {preview && <div className="mt-4"><div className="flex items-center justify-between"><p className="text-sm font-semibold">Text of {preview.name}</p><button className="text-xs underline" onClick={() => setPreview(null)}>Close</button></div><pre className="mt-1 max-h-60 overflow-auto whitespace-pre-wrap rounded-xl bg-soft p-3 text-xs">{preview.text || "(no extractable text)"}</pre></div>}</section>
      <section className="card" aria-labelledby="rp-h"><h2 id="rp-h" className="text-lg font-bold">Create a report</h2>
        <div className="mt-3 space-y-3"><div><label className="label" htmlFor="rt">Title</label><input id="rt" className="input" value={title} onChange={(e) => setTitle(e.target.value)} /></div><div><label className="label" htmlFor="rx">Text</label><textarea id="rx" className="input py-3" rows={6} value={text} onChange={(e) => setText(e.target.value)} /></div>
          <button className="btn-primary" disabled={busy || !title.trim() || !text.trim()} onClick={() => void run(async () => { await api("/studio/report", { body: { title, text } }); setTitle(""); setText(""); }, "Report created as a real PDF.")}>Create PDF</button></div></section>
    </div>
  );
}
