"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Empty, ErrorNote, PageTitle, Tag } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { when } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

type Status = { state: string; web_call: boolean; outbound: boolean; webhook_configured: boolean; consent: { voice_call: boolean; call_recording: boolean }; disclosure: string };
type Call = { id: string; kind: string; status: string; execution_id: string | null; duration_seconds: number | null; cost: number | null; error_code: string | null; created_at: string; transcript: string | null };
type Web = { start(): Promise<void>; stop(): Promise<void>; getRunId(): string | null; getState(): string; setMuted(m: boolean): void; on(e: string, h: (p?: unknown) => void): void };

const ERR: Record<string, string> = {
  microphone_denied: "Microphone access was blocked. Allow it in your browser’s site settings and try again.",
  at_capacity: "All voice lines are busy right now. Try again shortly.",
  mint_failed: "REDEEM could not open a call session.", connect_failed: "Could not connect. Check your network and retry.",
  call_rejected: "The voice provider declined the call.", autoplay_blocked: "Your browser blocked audio. Click Start call again.",
};

export default function VoiceStudio() {
  const { lang } = useI18n();
  const [status, setStatus] = useState<Status | null>(null);
  const [calls, setCalls] = useState<Call[]>([]);
  const [state, setState] = useState("idle");
  const [vol, setVol] = useState(0);
  const [muted, setMuted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const call = useRef<Web | null>(null);
  const callId = useRef<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setStatus(await api<Status>("/voice/status"));
      setCalls((await api<{ items: Call[] }>("/voice/calls")).items);
    } catch (e) { setError(e instanceof ApiError ? e.message : "Failed to load voice status"); }
  }, []);
  useEffect(() => { void refresh(); return () => { void call.current?.stop(); }; }, [refresh]);

  const setConsent = async (purpose: "voice_call" | "call_recording", granted: boolean) => {
    await api("/voice/consent", { body: { purpose, granted } }); await refresh();
  };

  const start = async () => {
    setError(null);
    try {
      const { BolnaWebCall } = await import("@bolna/web-call");
      const csrfHeader = (await api<{ csrf_token: string }>("/auth/me")).csrf_token;
      const c = new BolnaWebCall({
        getSession: async () => {
          const r = await fetch("/api/v1/voice/session", { method: "POST", headers: { "X-CSRF-Token": csrfHeader }, credentials: "same-origin" });
          const body = await r.json();
          if (!r.ok) throw new Error(body?.error?.code ?? "mint_failed");
          callId.current = r.headers.get("x-redeem-call-id");
          return body;
        },
      }) as unknown as Web;
      c.on("state-change", (s) => setState(String(s)));
      c.on("volume-level", (v) => setVol(Number(v)));
      c.on("call-start", async () => {
        const run = c.getRunId();
        if (run && callId.current) await api(`/voice/calls/${callId.current}/attach`, { body: { execution_id: run } }).catch(() => undefined);
        void refresh();
      });
      c.on("call-end", () => { setState("ended"); setVol(0); void refresh(); });
      c.on("error", (e) => { const code = (e as { code?: string })?.code ?? "unknown"; setError(ERR[code] ?? `Call error: ${code}`); });
      call.current = c;
      await c.start(); // inside the click handler → counts as a user gesture
    } catch (e) {
      setError(e instanceof Error && e.message === "PROVIDER_NOT_CONFIGURED" ? "Voice provider is not configured on this server." : ERR[(e as { code?: string })?.code ?? ""] ?? (e instanceof Error ? e.message : "Could not start the call"));
    }
  };
  const sync = async (id: string) => { try { await api(`/voice/calls/${id}/sync`, { method: "POST" }); await refresh(); } catch (e) { setError(e instanceof ApiError ? e.message : "Sync failed"); } };

  const live = state === "active" || state === "connecting" || state === "ringing";
  const ready = status?.state === "READY";
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageTitle title="Voice Studio" sub="Talk to the REDEEM voice agent in your browser, powered by Bolna." />
      <ErrorNote error={error} />
      <section className="card space-y-4" aria-labelledby="vs-h">
        <div className="flex flex-wrap items-center justify-between gap-2"><h2 id="vs-h" className="text-lg font-bold">Live call</h2>
          {status && <Tag tone={ready ? "teal" : "amber"}>{status.state}</Tag>}</div>
        {status && !ready && <p className="rounded-xl bg-amber-soft p-4 text-sm">Voice is <strong>not configured</strong> on this server (<code>BOLNA_API_KEY</code> and <code>BOLNA_AGENT_ID</code> are missing). No call is simulated. Everything else in REDEEM works without it.</p>}
        {status && (<fieldset className="space-y-2"><legend className="text-sm font-semibold">Consent</legend>
          <p className="text-sm text-muted">{status.disclosure}</p>
          <label className="flex min-h-[44px] items-center gap-3"><input type="checkbox" className="h-5 w-5" checked={status.consent.voice_call} onChange={(e) => void setConsent("voice_call", e.target.checked)} />I agree to speak with an AI voice agent.</label>
          <label className="flex min-h-[44px] items-center gap-3"><input type="checkbox" className="h-5 w-5" checked={status.consent.call_recording} onChange={(e) => void setConsent("call_recording", e.target.checked)} />Allow call recording (optional).</label></fieldset>)}
        <div className="flex flex-wrap items-center gap-3">
          {!live ? <button className="btn-teal" disabled={!ready || !status?.consent.voice_call} onClick={() => void start()}>Start call</button>
            : <button className="btn bg-danger text-deep" onClick={() => void call.current?.stop()}>End call</button>}
          <button className="btn-ghost" disabled={!live} onClick={() => { const n = !muted; call.current?.setMuted(n); setMuted(n); }} aria-pressed={muted}>{muted ? "Unmute" : "Mute"}</button>
          <span role="status" className="text-sm font-semibold capitalize">Connection: {state}</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-soft" aria-label="Agent voice level"><div className="h-full bg-teal transition-all" style={{ width: `${Math.round(vol * 100)}%` }} /></div>
        {ready && !status?.consent.voice_call && <p className="text-sm text-muted">Tick the consent box to enable the call button.</p>}
        <p className="text-xs text-muted">Languages verified live: <strong>none yet</strong>. Voice quality for Hindi, Tamil and Telugu depends on the agent’s configured ASR/TTS and must be tested before you rely on it.</p>
      </section>
      <section aria-labelledby="ch-h"><h2 id="ch-h" className="mb-3 text-lg font-bold">Call history</h2>
        {calls.length === 0 ? <Empty title="No calls yet">Only real calls placed through Bolna appear here.</Empty> : (
          <ul className="space-y-2">{calls.map((c) => (<li key={c.id} className="card p-4"><div className="flex flex-wrap items-center justify-between gap-2">
            <div><p className="font-semibold">{c.kind} call, {c.status}</p><p className="text-xs text-muted">{when(c.created_at, lang)}, execution {c.execution_id ?? "not yet correlated"}{c.duration_seconds != null && `, ${c.duration_seconds}s`}{c.cost != null && `, cost ${c.cost} (provider units)`}</p></div>
            <button className="btn-ghost" disabled={!c.execution_id} onClick={() => void sync(c.id)}>Refresh from Bolna</button></div>
            {c.transcript && <p className="mt-2 whitespace-pre-wrap text-sm text-muted">{c.transcript}</p>}</li>))}</ul>)}
      </section>
      <section className="card" aria-labelledby="vm-h"><h2 id="vm-h" className="text-lg font-bold">Voice memory</h2>
        <p className="mt-1 text-sm text-muted">Answers you give on a Bolna call can be mapped to your private memory (seat, meal, contact method, language…). Sensitive items wait for your confirmation, and only confirmed memory is used in later missions.</p>
        <div className="mt-3 flex flex-wrap gap-3"><Link className="btn-primary" href="/app/memory">Open Memory Center</Link><Link className="btn-ghost" href="/app/graph">See Memory Graph</Link><Link className="btn-ghost" href="/app/history">Conversation history</Link></div></section>
    </div>
  );
}
