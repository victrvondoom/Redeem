"use client";
import { useState } from "react";
import { ErrorNote } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

type Sec = { heading: string; paragraphs: string[]; bullets: string[] };
type S = { title: string; sections: Sec[]; action_items: string[]; facts: Record<string, string[]>; source_sha256: string; word_count: number };
type Out = { document_id: string; filename: string; pages: number; size: number; sha256: string; download: string; text_preview: string; duplicate: boolean };

/** Brief to PDF: paste a brief, review and edit the extracted structure, then render a real PDF stored (encrypted) in your Evidence Vault. */
export function BriefToPdf() {
  const [brief, setBrief] = useState("");
  const [s, setS] = useState<S | null>(null);
  const [out, setOut] = useState<Out | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<void>) => { setBusy(true); setError(null); try { await fn(); } catch (e) { setError(e instanceof ApiError ? e.message : "Failed"); } finally { setBusy(false); } };
  const edit = (i: number, patch: Partial<Sec>) => s && setS({ ...s, sections: s.sections.map((x, j) => (j === i ? { ...x, ...patch } : x)) });
  return (
    <section className="card space-y-4" aria-labelledby="brief-h">
      <h2 id="brief-h" className="text-2xl">Brief to PDF</h2>
      <p className="text-sm text-muted">Paste a brief. REDEEM pulls out headings, bullets, action items and key facts from your own words. Edit them, then render the PDF.</p>
      <ErrorNote error={error} />
      <div><label className="label" htmlFor="brief">Your brief</label><textarea id="brief" rows={6} className="input py-3" value={brief} onChange={(e) => { setBrief(e.target.value); setOut(null); }} placeholder={"# Title\nFindings:\n- A point\nWe should follow up by Friday."} /></div>
      <button className="btn-primary" disabled={busy || brief.trim().length < 10} onClick={() => void run(async () => { setS(await api<S>("/studio/brief/extract", { method: "POST", body: { brief } })); setOut(null); })}>Extract structure</button>
      {s && (<div className="space-y-4">
        <div><label className="label" htmlFor="b-title">Title</label><input id="b-title" className="input" value={s.title} onChange={(e) => setS({ ...s, title: e.target.value })} /></div>
        {s.sections.map((sec, i) => (<fieldset key={i} className="space-y-2 rounded-xl border border-line p-3"><legend className="px-1 text-sm font-semibold">Section {i + 1}</legend>
          <input aria-label={`Section ${i + 1} heading`} className="input" value={sec.heading} onChange={(e) => edit(i, { heading: e.target.value })} />
          <textarea aria-label={`Section ${i + 1} paragraphs`} rows={3} className="input py-2" value={sec.paragraphs.join("\n")} onChange={(e) => edit(i, { paragraphs: e.target.value.split("\n").filter(Boolean) })} />
          <textarea aria-label={`Section ${i + 1} bullets`} rows={3} className="input py-2" value={sec.bullets.join("\n")} onChange={(e) => edit(i, { bullets: e.target.value.split("\n").filter(Boolean) })} /></fieldset>))}
        <div><label className="label" htmlFor="b-act">Action items, one per line</label><textarea id="b-act" rows={3} className="input py-2" value={s.action_items.join("\n")} onChange={(e) => setS({ ...s, action_items: e.target.value.split("\n").filter(Boolean) })} /></div>
        <p className="text-sm text-muted">Found: {Object.entries(s.facts).filter(([, v]) => v.length).map(([k, v]) => `${k} ${v.join(", ")}`).join("; ") || "no dates, amounts or references"}.</p>
        <button className="btn-primary" disabled={busy} onClick={() => void run(async () => setOut(await api<Out>("/studio/brief/render", { method: "POST", body: { structured: s } })))}>Generate PDF</button></div>)}
      {out && (<div role="status" className="rounded-xl bg-soft p-4 text-sm"><p><strong>{out.filename}</strong>, {out.pages} page(s), {out.size.toLocaleString("en-IN")} bytes, stored encrypted in your Evidence Vault{out.duplicate ? " (identical file already existed)" : ""}.</p>
        <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap text-xs text-muted">{out.text_preview}</pre><a className="btn-ghost mt-2" href={out.download}>Download PDF</a></div>)}
    </section>
  );
}
