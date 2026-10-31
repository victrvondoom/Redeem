"use client";
/* eslint-disable @next/next/no-img-element */
import Link from "next/link";
import { Composer } from "@/components/Composer";
import { DemoLogin } from "@/components/DemoLogin";
import { Intro, Reveal, Starfield } from "@/components/Cinematic";
import { HeroDeck, LiveStats, PipelineSim } from "@/components/Showcase";
import { SiteNav } from "@/components/SiteNav";
import { Logo } from "@/components/ui";
import { useI18n } from "@/lib/i18n";

const STEPS: [string, string][] = [["Understand", "Voice or text, five languages."], ["Plan", "Options ranked, nothing run yet."], ["Approve", "Bound to exact target and amount."], ["Verify", "Read back before reporting."]];
const DOMAINS: [string, string][] = [["Travel", "Refunds, rebooking"], ["Banking", "Disputes, scam checks"], ["Insurance", "Claims, evidence"], ["Telecom", "Billing, outages"],
  ["Retail", "Returns, refunds"], ["Housing", "Deposits, repairs"], ["Government", "Grievances, RTI"], ["Healthcare admin", "Billing, records"]];
const WORKS: string[] = ["Eight case workflows", "Real browser on fixtures", "Encrypted memory", "Verified receipts"];
const NOT_YET: string[] = ["Live Bolna calls", "Real filing or email", "Image OCR", "Browser skills"];

export default function Landing() {
  const { t } = useI18n();
  return (
    <>
      <Intro />
      <SiteNav />
      <main id="main">
        <section id="product" className="relative overflow-hidden">
          <div className="rings" aria-hidden="true" /><Starfield />
          <div className="relative mx-auto grid max-w-6xl items-center gap-6 px-4 pb-20 pt-16 sm:px-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
            <div className="rise">
              <h1 className="pixel text-[2.9rem] leading-[1.08] sm:text-7xl">{t("hero.title1")}<br />{t("hero.title2")}</h1>
              <p className="mt-6 max-w-xl text-lg text-muted">{t("hero.sub")}</p>
              <div className="mt-8 flex flex-col gap-3 sm:flex-row"><a href="#start" className="btn-primary">{t("hero.cta1")}</a><a href="#watch" className="btn-ghost">Watch the engine</a><DemoLogin className="btn-ghost" label="Demo login" /></div>
            </div>
            <div className="rise" style={{ animationDelay: ".25s" }}><HeroDeck /></div>
          </div>
        </section>

        <section aria-label="Live counters" className="mx-auto max-w-6xl px-4 pb-40 sm:px-6"><Reveal><LiveStats /></Reveal></section>

        <section id="watch" className="mx-auto grid max-w-6xl scroll-mt-24 gap-10 px-4 pb-44 sm:px-6 lg:grid-cols-2">
          <Reveal from="left"><h2 className="text-4xl">Watch a mission run, then check the proof.</h2>
            <p className="mt-4 max-w-md text-muted">Every step is written to a ledger you can verify.</p>
            <div className="mt-6 flex flex-wrap gap-3"><Link href="/register" className="btn-primary">Run it live</Link><a href="#how" className="btn-ghost">How it works</a></div></Reveal>
          <Reveal from="right"><PipelineSim /></Reveal>
        </section>

        <div id="start" className="mx-auto max-w-6xl scroll-mt-24 px-4 pb-32 sm:px-6"><Composer /></div>

        <section id="how" className="mx-auto max-w-6xl scroll-mt-24 px-4 pb-32 sm:px-6">
          <h2 className="text-4xl">{t("how.title")}</h2>
          <ol className="steps mt-10 grid gap-x-10 gap-y-8 sm:grid-cols-2 lg:grid-cols-4">{STEPS.map(([h, d]) => (<li key={h} className="step border-t border-line pt-4"><h3 className="mt-2 text-xl font-bold">{h}</h3><p className="mt-1 text-muted">{d}</p></li>))}</ol>
        </section>

        <section id="solutions" className="mx-auto max-w-6xl scroll-mt-24 px-4 pb-32 sm:px-6">
          <h2 className="text-4xl">Eight domains, each a real workflow.</h2>
          <dl className="mt-10 grid gap-x-16 md:grid-cols-2">{DOMAINS.map(([n, d]) => (<div key={n} className="flex items-baseline justify-between gap-4 border-t border-line py-4"><dt className="text-xl font-bold">{n}</dt><dd className="text-right text-muted">{d}</dd></div>))}</dl>
        </section>

        <section id="business" className="mx-auto max-w-6xl scroll-mt-24 px-4 pb-32 sm:px-6">
          <div id="security" className="grid gap-10 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
            <div><h2 className="text-4xl">Checked, not claimed.</h2><p className="mt-4 max-w-md text-lg text-muted">An acknowledgement is not proof. REDEEM reads the result back before it says done.</p></div>
            <ul className="space-y-4 text-lg"><li className="border-t border-line pt-4">Approvals bind to the exact target and amount.</li><li className="border-t border-line pt-4">Lost replies are looked up, never resent.</li><li className="border-t border-line pt-4">Your memory is encrypted and yours to delete.</li></ul>
          </div>
        </section>

        <section id="developers" className="mx-auto max-w-6xl scroll-mt-24 px-4 pb-32 sm:px-6">
          <h2 className="text-4xl">What is real today.</h2>
          <div className="mt-10 grid gap-10 md:grid-cols-2">
            <div><h3 className="text-xl font-bold">Works</h3><ul className="mt-3 space-y-2 text-muted">{WORKS.map((w) => <li key={w} className="border-t border-line pt-2">{w}</li>)}</ul></div>
            <div><h3 className="text-xl font-bold">Not yet</h3><ul className="mt-3 space-y-2 text-muted">{NOT_YET.map((w) => <li key={w} className="border-t border-line pt-2">{w}</li>)}</ul></div>
          </div>
        </section>

        <section id="buildathon" className="mx-auto max-w-6xl scroll-mt-24 px-4 pb-32 sm:px-6">
          <div className="grid items-center gap-10 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
            <div><h2 className="text-4xl">Built for the Y Combinator <span className="font-sans">×</span> Symphony Buildathon.</h2>
              <p className="mt-4 max-w-lg text-lg text-muted">A hackathon prototype made with Bolna, 15 October to 20 November 2026. Many features are unfinished.</p></div>
            <div className="flex flex-wrap items-center gap-6">
              <a href="https://www.ycombinator.com" target="_blank" rel="noreferrer" aria-label="Y Combinator"><img src="/brand/ycombinator.png" alt="Y Combinator logo" width={112} height={99} className="h-24 w-auto rounded-xl" /></a>
              <a href="https://www.bolna.ai" target="_blank" rel="noreferrer" aria-label="Bolna"><img src="/brand/bolna-buildathon.png" alt="Bolna, voice AI agents" width={331} height={175} className="h-28 w-auto rounded-xl border border-line" /></a>
            </div>
          </div>
        </section>

        <section className="relative overflow-hidden border-t border-line px-4 py-28 text-center sm:px-6"><div className="rings" aria-hidden="true" />
          <h2 className="relative text-5xl">{t("hero.title1")} {t("hero.title2")}</h2><Link href="/register" className="btn-primary relative mt-8">{t("nav.start")}</Link></section>
      </main>
      <footer className="border-t border-line px-4 py-8 text-sm text-muted sm:px-6"><div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3"><Logo />
        <button className="btn-ghost" onClick={() => window.dispatchEvent(new Event("redeem:intro"))}>Replay intro</button>
        <p>Not endorsed by Bolna, Symphony or Y Combinator.</p></div></footer>
    </>
  );
}
