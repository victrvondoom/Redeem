"use client";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, Tag } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

type P = { provider: string; label: string; auth: string; configured: boolean; missing_config: string[]; state: string; account: string | null; scopes: string[]; last_verified_at: string | null;
  last_error: string | null; operations: string[]; needs: string | null; live_verified: boolean; calls_recorded?: number };
type A = { id: string; kind: string; params: Record<string, unknown>; digest: string; status: string; provider_ref: string | null; verification: Record<string, unknown> | null; error: string | null; created_at: string };
const TONE: Record<string, "teal" | "amber" | "danger" | "soft"> = { VERIFIED: "teal", DONE: "teal", APPROVED: "amber", DRAFT: "soft", UNCERTAIN: "amber", UNVERIFIED: "amber", FAILED: "danger", EXECUTING: "amber" };

export function Integrations() {
  const [ps, setPs] = useState<P[] | null>(null);
  const [acts, setActs] = useState<A[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [caps, setCaps] = useState<{ calendar: boolean; email: boolean }>({ calendar: true, email: true });
  const [kind, setKind] = useState<"calendar.create_event" | "email.send">("calendar.create_event");
  const [f, setF] = useState({ summary: "", start: "", end: "", to: "", subject: "", body: "" });

  const load = useCallback(async () => {
    try { setPs((await api<{ providers: P[] }>("/integrations")).providers); setActs((await api<{ items: A[] }>("/integrations/actions")).items); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Could not load integrations"); }
  }, []);
  useEffect(() => {
    void load();
    const q = new URLSearchParams(window.location.search);
    if (q.get("connected")) setNote(`Connected ${q.get("connected")}. Press Test to verify it with Google.`);
    if (q.get("error")) setError(`Connection was not completed: ${q.get("error")}`);
  }, [load]);
  const act = async (fn: () => Promise<unknown>) => { setBusy(true); setError(null); try { await fn(); await load(); } catch (e) { setError(e instanceof ApiError ? e.message : "Failed"); } finally { setBusy(false); } };
  const google = ps?.find((p) => p.provider === "google");
  const connect = () => act(async () => { const r = await api<{ auth_url: string }>("/integrations/google/connect", { method: "POST", body: { capabilities: (Object.keys(caps) as (keyof typeof caps)[]).filter((k) => caps[k]) } }); window.location.href = r.auth_url; });
  const draft = () => act(async () => {
    const params = kind === "calendar.create_event" ? { summary: f.summary, start: f.start, end: f.end, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone } : { to: f.to.split(/[,\s]+/).filter(Boolean), subject: f.subject, body: f.body };
    await api("/integrations/actions", { method: "POST", body: { kind, params } });
  });
  return (
    <section className="space-y-4" aria-labelledby="live-h">
      <h2 id="live-h" className="text-2xl">Live providers</h2>
      <ErrorNote error={error} />
      {note && <p role="status" className="rounded-xl bg-soft p-3 text-sm">{note}</p>}
      <ul className="grid gap-4 md:grid-cols-2">{ps?.map((p) => (
        <li key={p.provider} className="card">
          <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-lg font-bold">{p.label}</h3>
            <Tag tone={p.state === "connected" ? "teal" : p.state === "configured" ? "amber" : p.state === "error" ? "danger" : "soft"}>{p.state.replaceAll("_", " ")}</Tag></div>
          <p className="mt-1 text-sm text-muted">{p.auth}</p>
          {p.account && <p className="mt-2 text-sm">Account: <strong>{p.account}</strong></p>}
          {p.missing_config.length > 0 && <p className="mt-2 text-sm">Missing configuration: <span className="font-mono text-amber">{p.missing_config.join(", ")}</span></p>}
          {p.needs && <p className="mt-2 text-sm text-muted">{p.needs}</p>}
          <p className="mt-2 text-sm text-muted">{p.live_verified ? `Verified live${p.last_verified_at ? ` on ${new Date(p.last_verified_at).toLocaleString()}` : ""}.` : "Not verified live yet."}{p.provider === "bolna" ? ` ${p.calls_recorded ?? 0} call(s) recorded.` : ""}</p>
          {p.last_error && <p className="mt-1 text-sm text-danger">Last error: {p.last_error}</p>}
          <ul className="mt-2 list-disc pl-5 text-sm text-muted">{p.operations.map((o) => <li key={o}>{o}</li>)}</ul>
          {p.scopes.length > 0 && <details className="mt-2 text-sm"><summary className="cursor-pointer text-muted">Granted scopes ({p.scopes.length})</summary><ul className="mt-1 break-all font-mono text-xs text-muted">{p.scopes.map((s) => <li key={s}>{s}</li>)}</ul></details>}
          {p.provider === "google" && (<div className="mt-3 space-y-3">
            <fieldset className="flex flex-wrap gap-4 text-sm"><legend className="sr-only">Capabilities to request</legend>
              {(["calendar", "email"] as const).map((k) => <label key={k} className="flex min-h-[44px] items-center gap-2"><input type="checkbox" className="h-5 w-5 accent-[rgb(255,122,26)]" checked={caps[k]} onChange={(e) => setCaps({ ...caps, [k]: e.target.checked })} />{k === "calendar" ? "Calendar events" : "Send email"}</label>)}</fieldset>
            <div className="flex flex-wrap gap-2"><button className="btn-primary" disabled={busy || !p.configured || (!caps.calendar && !caps.email)} onClick={() => void connect()}>{p.state === "connected" ? "Reconnect" : "Connect Google"}</button>
              <button className="btn-ghost" disabled={busy || p.state !== "connected"} onClick={() => void act(async () => { const r = await api<{ account: string }>("/integrations/google/test", { method: "POST" }); setNote(`Google confirmed ${r.account}.`); })}>Test</button>
              <button className="btn-ghost text-danger" disabled={busy || !["connected", "error"].includes(p.state)} onClick={() => void act(async () => { const r = await api<{ revoked_at_provider: boolean; queued_actions_stopped: number }>("/integrations/google/disconnect", { method: "POST" }); setNote(`Disconnected. Revoked at Google: ${r.revoked_at_provider ? "yes" : "no (cleared locally)"}. Queued actions stopped: ${r.queued_actions_stopped}.`); })}>Disconnect</button></div></div>)}
        </li>))}</ul>

      {google?.state === "connected" && (
        <div className="card" aria-labelledby="act-h">
          <h3 id="act-h" className="text-lg font-bold">Act through Google</h3>
          <p className="mt-1 text-sm text-muted">Nothing is created or sent until you approve the exact draft. Results are read back from Google before they count as done.</p>
          <div className="mt-3 flex gap-2" role="radiogroup" aria-label="Operation">{(["calendar.create_event", "email.send"] as const).map((k) => <button key={k} role="radio" aria-checked={kind === k} onClick={() => setKind(k)} className={`badge min-h-[40px] px-4 ${kind === k ? "bg-teal text-deep" : "bg-soft text-muted"}`}>{k === "email.send" ? "Send email" : "Create calendar event"}</button>)}</div>
          {kind === "calendar.create_event" ? (<div className="mt-3 grid gap-3 md:grid-cols-3">
            <div className="md:col-span-3"><label className="label" htmlFor="x-sum">Title</label><input id="x-sum" className="input" value={f.summary} onChange={(e) => setF({ ...f, summary: e.target.value })} /></div>
            <div><label className="label" htmlFor="x-st">Starts</label><input id="x-st" type="datetime-local" className="input" value={f.start} onChange={(e) => setF({ ...f, start: e.target.value + ":00" })} /></div>
            <div><label className="label" htmlFor="x-en">Ends</label><input id="x-en" type="datetime-local" className="input" value={f.end} onChange={(e) => setF({ ...f, end: e.target.value + ":00" })} /></div></div>)
            : (<div className="mt-3 grid gap-3"><div><label className="label" htmlFor="x-to">To (comma separated)</label><input id="x-to" className="input" value={f.to} onChange={(e) => setF({ ...f, to: e.target.value })} /></div>
              <div><label className="label" htmlFor="x-sub">Subject</label><input id="x-sub" className="input" value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })} /></div>
              <div><label className="label" htmlFor="x-body">Message</label><textarea id="x-body" rows={4} className="input py-3" value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} /></div></div>)}
          <button className="btn-primary mt-3" disabled={busy} onClick={() => void draft()}>Prepare draft</button>
        </div>)}

      {acts.length > 0 && (<div className="space-y-3"><h3 className="text-lg font-bold">Recent actions</h3>
        <ul className="space-y-3">{acts.map((a) => (<li key={a.id} className="card !p-4">
          <div className="flex flex-wrap items-center justify-between gap-2"><span className="font-semibold">{a.kind === "email.send" ? `Email to ${(a.params.to as string[]).join(", ")}: ${a.params.subject}` : `Calendar event: ${a.params.summary}`}</span><Tag tone={TONE[a.status] ?? "soft"}>{a.status.toLowerCase()}</Tag></div>
          <p className="mt-1 text-xs text-muted">Approval digest {a.digest.slice(0, 12)}…{a.provider_ref ? `, provider id ${a.provider_ref.slice(0, 16)}` : ""}</p>
          {a.verification && <p className="mt-1 text-sm text-muted">Read-back: {JSON.stringify(a.verification)}</p>}
          {a.error && <p className="mt-1 text-sm text-danger">{a.error.replaceAll("_", " ")}</p>}
          <div className="mt-2 flex flex-wrap gap-2">
            {a.status === "DRAFT" && <button className="btn-teal !min-h-[40px]" disabled={busy} onClick={() => void act(() => api(`/integrations/actions/${a.id}/approve`, { method: "POST", body: { digest: a.digest } }))}>Approve exactly this</button>}
            {a.status === "APPROVED" && <button className="btn-primary !min-h-[40px]" disabled={busy} onClick={() => void act(() => api(`/integrations/actions/${a.id}/execute`, { method: "POST" }))}>Run now</button>}
            {a.status === "UNCERTAIN" && <button className="btn-ghost !min-h-[40px]" disabled={busy} onClick={() => void act(() => api(`/integrations/actions/${a.id}/reconcile`, { method: "POST" }))}>Check at Google (read-only)</button>}
          </div></li>))}</ul></div>)}
    </section>
  );
}
