"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, type Lang, type Mission } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { LANG_LABEL, SPEECH_LANG } from "@/lib/messages";
import { ErrorNote } from "./ui";

type Rec = { lang: string; interimResults: boolean; continuous: boolean; start(): void; stop(): void;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string; confidence: number }>> }) => void) | null;
  onend: (() => void) | null; onerror: ((e: { error: string }) => void) | null };
type RecCtor = new () => Rec;
const PENDING = "redeem_pending_intent";

export function Composer({ compact = false }: { compact?: boolean }) {
  const { t, lang, setLang } = useI18n();
  const { me } = useAuth();
  const router = useRouter();
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const [source, setSource] = useState<"text" | "voice">("text");
  const [confidence, setConfidence] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [supported, setSupported] = useState(true);
  const rec = useRef<Rec | null>(null);

  useEffect(() => {
    const w = window as unknown as { SpeechRecognition?: RecCtor; webkitSpeechRecognition?: RecCtor };
    setSupported(Boolean(w.SpeechRecognition ?? w.webkitSpeechRecognition));
  }, []);

  const toggleMic = () => {
    if (listening) { rec.current?.stop(); return; }
    const w = window as unknown as { SpeechRecognition?: RecCtor; webkitSpeechRecognition?: RecCtor };
    const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
    if (!Ctor) { setError(t("composer.micUnsupported")); return; }
    setError(null);
    const r = new Ctor();
    r.lang = SPEECH_LANG[lang]; r.interimResults = false; r.continuous = false;
    r.onresult = (e) => {
      const alt = e.results[0][0];
      setText(alt.transcript); setSource("voice"); setConfidence(alt.confidence || null);
      if (alt.confidence && alt.confidence < 0.6) setError(t("composer.lowConfidence"));
    };
    r.onerror = (e) => { setError(e.error === "not-allowed" ? "Microphone permission was denied." : `Speech recognition error: ${e.error}`); setListening(false); };
    r.onend = () => setListening(false);
    rec.current = r; setListening(true); r.start();
  };

  const submit = async () => {
    const intent = text.trim();
    if (intent.length < 3) { setError("Please describe the problem in a few words."); return; }
    const payload = { intent, language: lang, source, transcript_confidence: source === "voice" ? confidence : null };
    if (!me) {
      try { sessionStorage.setItem(PENDING, JSON.stringify(payload)); } catch { /* fall through */ }
      router.push("/register?next=/app");
      return;
    }
    setBusy(true); setError(null);
    try {
      const m = await api<Mission>("/missions", { body: payload });
      router.push(`/app/missions/${m.id}`);
    } catch (e) { setError(e instanceof ApiError ? e.message : "Could not start the mission."); setBusy(false); }
  };

  const prompts = ["p.1", "p.2", "p.3"].map((k) => t(k));
  return (
    <section aria-labelledby="composer-h" className={`card ${compact ? "" : "mx-auto max-w-3xl"}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="composer-h" className="text-lg font-bold">{t("composer.title")}</h2>
        <label className="flex items-center gap-2 text-sm"><span className="font-semibold">{t("composer.language")}</span>
          <select value={lang} onChange={(e) => setLang(e.target.value as Lang)} className="min-h-[44px] rounded-xl border border-line bg-surface px-3 text-sm font-semibold">
            {(Object.keys(LANG_LABEL) as Lang[]).map((l) => <option key={l} value={l}>{LANG_LABEL[l]}</option>)}
          </select></label>
      </div>
      <label htmlFor="intent" className="sr-only">{t("composer.placeholder")}</label>
      <textarea id="intent" value={text} onChange={(e) => { setText(e.target.value); setSource("text"); }} rows={3} maxLength={2000}
        placeholder={t("composer.placeholder")} className="input mt-4 resize-y py-3" />
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button type="button" onClick={toggleMic} disabled={!supported && !listening} aria-pressed={listening}
          className={`btn-ghost ${listening ? "listening border-teal text-teal" : ""}`}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><rect x="9" y="2" width="6" height="12" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v4" /></svg>
          {listening ? t("composer.stop") : t("composer.mic")}
        </button>
        <button type="button" onClick={() => void submit()} disabled={busy} className="btn-primary">{t("composer.submit")}</button>
        <span aria-live="polite" className="text-sm text-teal">{listening ? t("composer.listening") : ""}</span>
      </div>
      <p className="mt-3 text-xs text-muted">{supported ? t("composer.micNote") : t("composer.micUnsupported")}</p>
      <div className="mt-3"><ErrorNote error={error} /></div>
      <div className="mt-5">
        <p className="mb-2 text-sm font-semibold text-muted">{t("composer.suggested")}</p>
        <ul className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
          {prompts.map((p) => (<li key={p}><button type="button" onClick={() => { setText(p); setSource("text"); }}
            className="min-h-[44px] w-full rounded-xl border border-line bg-soft px-4 py-2 text-left text-sm hover:border-indigo sm:w-auto">{p}</button></li>))}
        </ul>
      </div>
    </section>
  );
}

export const takePending = (): { intent: string; language: Lang; source: "text" | "voice"; transcript_confidence: number | null } | null => {
  try {
    const raw = sessionStorage.getItem(PENDING);
    if (!raw) return null;
    sessionStorage.removeItem(PENDING);
    return JSON.parse(raw);
  } catch { return null; }
};
