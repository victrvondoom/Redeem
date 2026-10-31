"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { ErrorNote, PageTitle, Tag } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

type Dev = { id: string; name: string; kind: string; platform: string; online: boolean; device_state: string | null };
type Frame = { id: string; url: string; width: number; height: number; origin_x: number; origin_y: number; active_window: { title?: string; app?: string } | null; captured_at: string };
type Act = { id: string; actor: string; action: string; params: Record<string, unknown>; reason: string; target: { label?: string; bbox?: { x: number; y: number; w: number; h: number }; frame_id?: string } | null; risk: string; status: string; error: string | null; after_frame_id: string | null; at: string };
type Task = { id: string; instruction: string; source: string; status: string; step: string | null; report: { summary?: string } | null; pending_approval: { digest: string; action: string; target?: { label?: string } } | null };
type Live = { session: { id: string; mode: string; status: string }; device: Dev | null; frame: Frame | null; tasks: Task[]; actions: Act[] };

const TONE: Record<string, "teal" | "amber" | "danger" | "soft"> = { ACTIVE: "teal", DONE: "teal", RUNNING: "amber", PAUSED: "amber", USER_CONTROL: "amber", NEEDS_APPROVAL: "amber", FAILED: "danger", STOPPED: "danger", UNCERTAIN: "danger", BLOCKED: "amber" };

export default function LiveComputer() {
  const [devs, setDevs] = useState<Dev[]>([]);
  const [code, setCode] = useState<string | null>(null);
  const [live, setLive] = useState<Live | null>(null);
  const [sid, setSid] = useState<string | null>(null);
  const [cmd, setCmd] = useState("Open the CRM on my computer. Find Priya Sharma, update her preferred contact method to WhatsApp, create a follow-up for tomorrow at 10 AM, and prepare a message draft. Do not send it.");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const img = useRef<HTMLImageElement>(null);
  const fail = (e: unknown, m: string) => setError(e instanceof ApiError ? e.message : m);

  const loadDevs = useCallback(async () => { try { setDevs((await api<{ items: Dev[] }>("/computer/devices")).items); } catch (e) { fail(e, "Could not load computers"); } }, []);
  useEffect(() => { void loadDevs(); }, [loadDevs]);
  useEffect(() => {
    if (!sid) return;
    let stop = false;
    const tick = async () => { try { const l = await api<Live>(`/computer/sessions/${sid}/live`); if (!stop) setLive(l); } catch { /* keep last state */ } if (!stop) setTimeout(tick, 900); };
    void tick();
    return () => { stop = true; };
  }, [sid]);

  const run = async (f: () => Promise<void>, m: string) => { setBusy(true); setError(null); try { await f(); } catch (e) { fail(e, m); } finally { setBusy(false); } };
  const pair = () => run(async () => setCode((await api<{ code: string }>("/computer/pairing-codes", { method: "POST" })).code), "Could not create a code");
  const open = (d: Dev) => run(async () => setSid((await api<Live>("/computer/sessions", { method: "POST", body: { device_id: d.id } })).session.id), "Could not connect");
  const cloud = () => run(async () => { const l = await api<Live>("/computer/cloud", { method: "POST" }); setSid(l.session.id); await loadDevs(); }, "Could not start a cloud computer");
  const ctl = (op: string) => run(async () => { await api(`/computer/sessions/${sid}/control`, { method: "POST", body: { op } }); if (op === "end") { setSid(null); setLive(null); await loadDevs(); } }, "Control failed");
  const task = () => run(async () => { await api(`/computer/sessions/${sid}/tasks`, { method: "POST", body: { instruction: cmd } }); }, "Could not start the task");
  const approve = (t: Task) => run(async () => { await api(`/computer/tasks/${t.id}/approve`, { method: "POST", body: { digest: t.pending_approval!.digest } }); }, "Approval failed");
  const reject = (t: Task) => run(async () => { await api(`/computer/tasks/${t.id}/reject`, { method: "POST" }); }, "Could not decline");
  const userClick = (e: React.MouseEvent<HTMLImageElement>) => {
    if (live?.session.status !== "USER_CONTROL" || !live.frame || !img.current) return;
    const r = img.current.getBoundingClientRect();
    const x = Math.round(live.frame.origin_x + ((e.clientX - r.left) / r.width) * live.frame.width), y = Math.round(live.frame.origin_y + ((e.clientY - r.top) / r.height) * live.frame.height);
    void run(async () => { await api(`/computer/sessions/${sid}/input`, { method: "POST", body: { action: "click_coordinates", params: { x, y } } }); }, "Click failed");
  };

  const s = live?.session, f = live?.frame, t = live?.tasks[0];
  const lastTarget = live?.actions.find((a) => a.target?.bbox && a.target.frame_id);
  const box = lastTarget?.target?.bbox && f ? lastTarget.target.bbox : null;

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      <PageTitle title="Live Computer" sub="REDEEM operates a real computer: it reads the screen, moves the mouse, types, and checks the result. You can pause, take over or stop at any moment." />
      <ErrorNote error={error} />
      {!sid && (
        <div className="grid gap-4 md:grid-cols-2">
          <section className="card space-y-3" aria-labelledby="mine-h">
            <h2 id="mine-h" className="text-lg font-bold">My computer</h2>
            <p className="text-sm text-muted">Install the REDEEM Computer Bridge on your Windows PC (<code>pip install ./apps/bridge</code>), then pair it with a one-time code. The bridge connects out to REDEEM; nothing is opened on your PC.</p>
            <button className="btn-primary" disabled={busy} onClick={pair}>Connect my computer</button>
            {code && <p className="rounded-lg bg-soft p-3 text-sm">Code (valid 10 minutes, one use): <span className="font-mono text-lg font-bold" data-testid="pair-code">{code}</span><br /><code className="text-xs">python -m redeem_bridge pair --server {typeof window !== "undefined" ? window.location.origin : ""} --code {code}</code></p>}
            <ul className="space-y-2">{devs.filter((d) => d.kind !== "cloud").map((d) => (<li key={d.id} className="flex items-center justify-between gap-2 rounded-lg bg-soft px-3 py-2"><span>{d.name} <span className="text-xs text-muted">{d.platform}</span></span><span className="flex items-center gap-2"><Tag tone={d.online ? "teal" : "soft"}>{d.online ? "online" : "offline"}</Tag><button className="btn-ghost !py-1" disabled={!d.online || busy} onClick={() => open(d)}>Open</button><button className="btn-ghost !py-1" onClick={() => run(async () => { await api(`/computer/devices/${d.id}`, { method: "DELETE" }); await loadDevs(); }, "Revoke failed")}>Revoke</button></span></li>))}</ul>
          </section>
          <section className="card space-y-3" aria-labelledby="cloud-h">
            <h2 id="cloud-h" className="text-lg font-bold">Cloud computer</h2>
            <p className="text-sm text-muted">A separate desktop with a real Chromium browser, started for you on the REDEEM server and deleted when you end it.</p>
            <button className="btn-primary" disabled={busy} onClick={cloud}>{busy ? "Starting…" : "Start a cloud computer"}</button>
          </section>
        </div>
      )}
      {sid && live && s && (
        <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
          <section className="card !p-3 space-y-2" aria-label="Computer screen">
            <div className="flex flex-wrap items-center justify-between gap-2 px-1">
              <div className="flex items-center gap-2"><Tag tone={TONE[s.status] ?? "soft"}>{s.status === "USER_CONTROL" ? "you have control" : s.status.toLowerCase()}</Tag><span className="text-sm">{live.device?.name}</span><span className="text-xs text-muted">{f?.active_window?.title || f?.active_window?.app || ""}</span></div>
              <span className="text-xs text-muted">Live screen updates (about 1 per second){f ? ` · ${new Date(f.captured_at).toLocaleTimeString()}` : ""}</span>
            </div>
            <div className="relative overflow-hidden rounded-lg border border-line bg-black">
              {f ? (<>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img ref={img} src={f.url} alt="The computer's screen as REDEEM last captured it" className={`w-full ${s.status === "USER_CONTROL" ? "cursor-crosshair" : ""}`} onClick={userClick} data-testid="live-frame" />
                {box && <div aria-hidden className="pointer-events-none absolute rounded border-2 border-accent motion-safe:transition-all" style={{ left: `${(box.x / f.width) * 100}%`, top: `${(box.y / f.height) * 100}%`, width: `${(box.w / f.width) * 100}%`, height: `${(box.h / f.height) * 100}%` }} />}
              </>) : <p className="p-10 text-center text-sm text-muted">Waiting for the first frame…</p>}
            </div>
            <div className="flex flex-wrap gap-2">
              {s.status === "PAUSED" ? <button className="btn-ghost" onClick={() => ctl("resume")}>Resume</button> : s.status === "ACTIVE" && <button className="btn-ghost" onClick={() => ctl("pause")}>Pause</button>}
              {s.status === "USER_CONTROL" ? <button className="btn-primary" onClick={() => ctl("release")}>Hand control back</button> : ["ACTIVE", "PAUSED"].includes(s.status) && <button className="btn-ghost" onClick={() => ctl("takeover")}>Take over</button>}
              {!["STOPPED", "ENDED"].includes(s.status) && <button className="btn-ghost !border-danger !text-danger" onClick={() => ctl("stop")}>Emergency stop</button>}
              <button className="btn-ghost" onClick={() => ctl("end")}>End session</button>
            </div>
            {s.status === "USER_CONTROL" && <p className="text-sm text-muted">REDEEM has stopped sending input. Click on the screen above to click on the computer{live.session.mode === "my_computer" ? ", or simply use your own mouse and keyboard" : ""}.</p>}
          </section>
          <aside className="space-y-4">
            <section className="card space-y-2" aria-labelledby="ask-h">
              <h2 id="ask-h" className="font-bold">Ask REDEEM</h2>
              <textarea className="input h-28 w-full text-sm" value={cmd} onChange={(e) => setCmd(e.target.value)} aria-label="Instruction" />
              <button className="btn-primary w-full" disabled={busy || s.status !== "ACTIVE" || ["RUNNING", "PLANNING"].includes(t?.status ?? "")} onClick={task}>Do it on this computer</button>
              <p className="text-xs text-muted">Spoken requests from a Bolna call arrive here the same way.</p>
            </section>
            {t && (
              <section className="card space-y-2" aria-live="polite" aria-labelledby="task-h">
                <div className="flex items-center justify-between"><h2 id="task-h" className="font-bold">Current task</h2><Tag tone={TONE[t.status] ?? "soft"}>{t.status.replaceAll("_", " ").toLowerCase()}</Tag></div>
                <p className="text-sm">{t.instruction}</p>
                {t.step && <p className="text-xs text-muted">Now: {t.step}</p>}
                {t.report?.summary && <p className="rounded-lg bg-soft p-2 text-sm" data-testid="task-summary">{t.report.summary}</p>}
                {t.status === "NEEDS_APPROVAL" && t.pending_approval && <div className="space-y-2 rounded-lg border border-accent p-2 text-sm"><p>Approve exactly this: <b>{t.pending_approval.action}</b> on “{t.pending_approval.target?.label}”.</p><div className="flex gap-2"><button className="btn-primary" onClick={() => approve(t)}>Approve</button><button className="btn-ghost" onClick={() => reject(t)}>Decline</button></div></div>}
              </section>
            )}
            <section className="card space-y-2" aria-labelledby="tl-h">
              <h2 id="tl-h" className="font-bold">What happened</h2>
              <ol className="max-h-[420px] space-y-1 overflow-auto text-sm">
                {live.actions.filter((a) => a.action !== "observe_screen").map((a) => (
                  <li key={a.id} className="flex items-start justify-between gap-2 border-b border-line py-1">
                    <span><span className="font-semibold">{a.actor === "user" ? "You" : "REDEEM"}</span> {a.action.replaceAll("_", " ")}{a.target?.label ? ` “${a.target.label}”` : ""}<span className="block text-xs text-muted">{a.reason}{a.error ? ` · ${a.error}` : ""}</span></span>
                    <Tag tone={TONE[a.status] ?? "soft"}>{a.status.toLowerCase()}</Tag>
                  </li>))}
              </ol>
            </section>
          </aside>
        </div>
      )}
    </div>
  );
}
