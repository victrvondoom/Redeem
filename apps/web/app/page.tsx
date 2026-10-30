"use client";
import Link from "next/link";
import { Composer } from "@/components/Composer";
import { SiteNav } from "@/components/SiteNav";
import { Logo, Tag } from "@/components/ui";
import { useI18n } from "@/lib/i18n";

const REAL_TODAY: [string, string, "teal" | "amber" | "soft"][] = [
  ["Flight-refund recovery mission", "Runs end-to-end against a stateful local fixture; no real airline is contacted", "teal"],
  ["Shop reservation mission", "Runs end-to-end against a stateful local shop fixture", "teal"],
  ["Bolna voice in the browser", "Implemented. Needs your Bolna credentials to place a live call", "amber"],
  ["Outbound phone calls", "Implemented behind an allow-list. Disabled unless an operator enables it", "amber"],
  ["Legal / regulatory citations", "Not shipped: no verified, dated source corpus yet", "soft"],
  ["Other domains (billing, health, telecom…)", "Planned. Listed honestly as not built", "soft"],
];

export default function Landing() {
  const { t } = useI18n();
  const steps = [1, 2, 3, 4];
  return (
    <>
      <SiteNav />
      <main id="main">
        <section id="product" className="mx-auto max-w-6xl px-4 pb-10 pt-12 text-center sm:px-6 sm:pt-20">
          <p className="h-eyebrow">{t("hero.eyebrow")}</p>
          <h1 className="mx-auto mt-3 max-w-3xl text-[2.5rem] font-extrabold leading-[1.1] tracking-tight sm:text-6xl">
            {t("hero.title1")}<br /><span className="text-indigo">{t("hero.title2")}</span>
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-lg text-muted">{t("hero.sub")}</p>
          <div className="mt-7 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <a href="#start" className="btn-primary w-full sm:w-auto">{t("hero.cta1")}</a>
            <a href="#how" className="btn-ghost w-full sm:w-auto">{t("hero.cta2")}</a>
          </div>
          <p className="mt-4 text-sm font-semibold text-muted">One voice. Every domain. Verified outcomes.</p>
        </section>

        <div id="start" className="mx-auto max-w-6xl scroll-mt-24 px-4 sm:px-6"><Composer /></div>

        <section id="how" className="mx-auto max-w-6xl scroll-mt-24 px-4 py-20 sm:px-6">
          <h2 className="text-3xl font-extrabold tracking-tight">{t("how.title")}</h2>
          <ol className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {steps.map((n) => (
              <li key={n} className="card">
                <span className="grid h-9 w-9 place-items-center rounded-full bg-indigo-soft font-extrabold text-indigo">{n}</span>
                <h3 className="mt-4 text-lg font-bold">{t(`how.${n}`)}</h3>
                <p className="mt-1 text-sm text-muted">{t(`how.${n}d`)}</p>
              </li>
            ))}
          </ol>
        </section>

        <section id="solutions" className="mx-auto grid max-w-6xl scroll-mt-24 gap-4 px-4 sm:px-6 md:grid-cols-2">
          <article className="card">
            <Tag tone="indigo">Consumer</Tag>
            <h3 className="mt-3 text-xl font-bold">Flight cancelled, refund missing</h3>
            <p className="mt-2 text-muted">REDEEM identifies the booking by reference (not just a name), prepares a refund request and a linked hotel change, shows the exact amount, and verifies what the desk actually received.</p>
          </article>
          <article id="business" className="card scroll-mt-24">
            <Tag tone="teal">Business</Tag>
            <h3 className="mt-3 text-xl font-bold">Shop call to confirmed reservation</h3>
            <p className="mt-2 text-muted">A caller wants a keyboard for Saturday. REDEEM checks live stock, picks the right customer record, reserves after approval, and reads the reservation back.</p>
          </article>
        </section>

        <section className="mx-auto mt-4 max-w-6xl px-4 sm:px-6">
          <div className="card grid gap-6 md:grid-cols-2">
            <div>
              <h2 className="text-2xl font-extrabold tracking-tight">Verified means checked, not claimed</h2>
              <p className="mt-2 text-muted">A provider saying “OK” is not proof. After every action a separate verifier reads the real state. If an acknowledgement is lost, REDEEM never blindly resends — it looks the request up first. If you change your mind mid-way, earlier approvals stop working.</p>
            </div>
            <ul className="space-y-2 text-sm">
              {["Approvals are bound to the exact target, amount and revision", "Write-ahead ledger before every side effect", "Lost acknowledgement → look up, never duplicate", "Receipt with a tamper-evident ledger hash"].map((x) => (
                <li key={x} className="flex gap-3 rounded-xl bg-soft px-4 py-3"><span aria-hidden className="text-teal">✓</span>{x}</li>))}
            </ul>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <h2 className="text-2xl font-extrabold tracking-tight">Languages</h2>
          <p className="mt-2 max-w-3xl text-muted">English, हिन्दी, Hinglish, தமிழ் and తెలుగు work in the interface and for mission text. Live voice quality per language still has to be verified against a configured Bolna agent — it is not claimed here.</p>
        </section>

        <section id="security" className="mx-auto max-w-6xl scroll-mt-24 px-4 sm:px-6">
          <div className="card">
            <h2 className="text-2xl font-extrabold tracking-tight">Permission and privacy controls</h2>
            <ul className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
              {["Nothing consequential runs without your approval", "Calls need explicit consent; recording is a separate opt-in", "Your API keys never reach the browser", "Per-workspace isolation, export and delete controls", "Callers are told they're speaking with an AI", "Revoke any connection at any time"].map((x) => (
                <li key={x} className="flex gap-3"><span aria-hidden className="text-teal">✓</span>{x}</li>))}
            </ul>
          </div>
        </section>

        <section id="developers" className="mx-auto max-w-6xl scroll-mt-24 px-4 py-16 sm:px-6">
          <h2 className="text-2xl font-extrabold tracking-tight">What is real today</h2>
          <p className="mt-2 text-muted">We list what works and what does not. No customer numbers or success rates are claimed because there are none yet.</p>
          <ul className="mt-6 divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
            {REAL_TODAY.map(([name, note, tone]) => (
              <li key={name} className="flex flex-col gap-1 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                <div><p className="font-semibold">{name}</p><p className="text-sm text-muted">{note}</p></div>
                <Tag tone={tone}>{tone === "teal" ? "Works (fixture)" : tone === "amber" ? "Needs credentials" : "Not built"}</Tag>
              </li>))}
          </ul>
        </section>

        <section className="bg-deep px-4 py-16 text-center text-white sm:px-6">
          <h2 className="text-3xl font-extrabold tracking-tight">{t("hero.title1")} {t("hero.title2")}</h2>
          <Link href="/register" className="btn mt-6 bg-white text-deep hover:bg-soft">{t("nav.start")}</Link>
        </section>
      </main>
      <footer className="border-t border-line px-4 py-8 text-sm text-muted sm:px-6">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3">
          <Logo /><p>Built for the Bolna × YC Symphony Buildathon 2026. Not endorsed by Bolna or Y Combinator.</p>
        </div>
      </footer>
    </>
  );
}
