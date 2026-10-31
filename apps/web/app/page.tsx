"use client";
import Link from "next/link";
import { Composer } from "@/components/Composer";
import { Icon } from "@/components/Icons";
import { Intro, Reveal, Starfield, Tilt } from "@/components/Cinematic";
import { HeroDeck, LiveStats, PipelineSim } from "@/components/Showcase";
import { SiteNav } from "@/components/SiteNav";
import { Logo, Tag } from "@/components/ui";
import { useI18n } from "@/lib/i18n";

const DOMAINS: [string, string, string][] = [
  ["Airline & travel", "Cancelled flight? Refund request, hotel and calendar fixes in one mission.", "mission"], ["Banking & payment safety", "Disputes, failed UPI payments, scam checks. Never asks for an OTP.", "shield"],
  ["Insurance", "Claim rejection checklist, evidence mapping, escalation to the ombudsman route.", "cases"], ["Telecom", "Billing and outage complaints with TRAI-sourced passages.", "voice"],
  ["E-commerce & retail", "Returns and refunds; a shop operator that reserves stock atomically.", "vault"], ["Housing & property", "Deposit, possession and maintenance complaints with RERA material.", "home"],
  ["Government grievances", "Grievance and RTI preparation with the right escalation ladder.", "book"], ["Healthcare administration", "Billing and records. Never diagnoses or advises on treatment.", "plug"],
];
const STEPS: [string, string][] = [["Understand", "Voice or text in five languages; domains and entities extracted, asking only for what is truly missing."], ["Gather evidence", "Documents read, classified and scored; every claim you make is checked against them."],
  ["Retrieve sources", "Passages from a knowledge base with provenance. No citation is ever invented."], ["Plan & rank", "Options ranked by benefit, time, risk and privacy. You can change the weights."],
  ["Approve", "Your approval is bound to the exact draft, target and amount. Change anything and it is void."], ["Execute", "APIs, a real browser, or a guided handoff. Nothing runs twice."], ["Verify", "A separate step reads the real state back. A success toast proves nothing."], ["Report", "A receipt and evidence bundle with a hash chain you can download."]];
const REAL: [string, string, "teal" | "amber" | "soft"][] = [
  ["Eight consumer-rights case workflows", "Intake, evidence checklist, retrieval, ranking, draft, approval, handoff, tracking. Tested.", "teal"], ["Real Chromium actions", "Before/after snapshots and a temporal guard, against simulated apps on loopback.", "teal"],
  ["Cross-domain missions with a task graph", "Refund + hotel + calendar + family draft, persisted, dependency-gated.", "teal"], ["Evidence vault & knowledge base", "1,159 passages (799 telecom + 290 e-commerce scraped by RECLAIM; ~70 authored guides). Insurance: none.", "teal"],
  ["Bolna voice", "Implemented and contract-tested. Needs your Bolna credentials; no live call has been made.", "amber"], ["Real filing with any authority", "Not available. REDEEM prepares everything and hands off; it never claims a filing it did not make.", "soft"],
  ["Real airline, bank or shop integrations", "Not available. Effects run on labelled local fixtures.", "soft"], ["OCR for images", "Not available here: images are stored, never given invented text.", "soft"],
];

export default function Landing() {
  const { t } = useI18n();
  return (
    <>
      <Intro />
      <SiteNav />
      <main id="main">
        <section id="product" className="relative overflow-hidden">
          <div className="rings" aria-hidden="true" /><Starfield /><div className="grid-floor" aria-hidden="true" />
          <div className="relative mx-auto grid max-w-6xl items-center gap-6 px-4 pb-16 pt-14 sm:px-6 sm:pt-24 lg:grid-cols-[1.15fr_1fr]">
            <div className="rise">
              <p className="h-eyebrow">{t("hero.eyebrow")}</p>
              <h1 className="pixel mt-4 text-[2.9rem] font-normal leading-[1.02] tracking-tight sm:text-7xl">{t("hero.title1")}<br /><span className="glow-text">{t("hero.title2")}</span></h1>
              <p className="mt-6 max-w-xl text-lg text-muted">{t("hero.sub")}</p>
              <div className="mt-8 flex flex-col gap-3 sm:flex-row"><a href="#start" className="btn-primary">{t("hero.cta1")}</a><a href="#watch" className="btn-ghost">Watch the engine</a></div>
              <p className="mt-5 text-sm font-semibold tracking-wide text-muted">One voice. Every domain. Verified outcomes.</p>
            </div>
            <div className="rise" style={{ animationDelay: ".25s" }}><HeroDeck /></div>
          </div>
        </section>

        <section aria-label="Live counters" className="mx-auto max-w-6xl px-4 pb-6 sm:px-6"><Reveal><LiveStats /></Reveal></section>

        <section id="watch" className="mx-auto grid max-w-6xl scroll-mt-24 gap-8 px-4 py-20 sm:px-6 lg:grid-cols-2">
          <Reveal from="left"><p className="h-eyebrow">The engine</p><h2 className="mt-3 text-4xl font-extrabold tracking-tight">Watch a mission run.<br /><span className="glow-text">Then check the proof.</span></h2>
            <p className="mt-4 text-muted">Every step lands in an append-only, hash-chained ledger. Nothing is called done until an independent read-back agrees.</p>
            <div className="mt-6 flex flex-wrap gap-3"><Link href="/register" className="btn-primary">Run it live</Link><a href="#how" className="btn-ghost">How it works</a></div></Reveal>
          <Reveal from="right"><PipelineSim /></Reveal>
        </section>
        <div id="start" className="mx-auto max-w-6xl scroll-mt-24 px-4 sm:px-6"><Composer /></div>

        <section id="how" className="mx-auto max-w-6xl scroll-mt-24 px-4 py-20 sm:px-6">
          <h2 className="text-3xl font-extrabold tracking-tight">{t("how.title")}</h2><p className="mt-2 max-w-2xl text-muted">One lifecycle for every domain. Each stage is saved, visible and resumable.</p>
          <ol className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{STEPS.map(([h, d], i) => (<li key={h} className="card"><span className="grid h-9 w-9 place-items-center rounded-full bg-indigo-soft font-extrabold text-indigo">{i + 1}</span><h3 className="mt-4 text-lg font-bold">{h}</h3><p className="mt-1 text-sm text-muted">{d}</p></li>))}</ol>
        </section>

        <section id="solutions" className="mx-auto max-w-6xl scroll-mt-24 px-4 sm:px-6">
          <h2 className="text-3xl font-extrabold tracking-tight">Eight domains, each with a real workflow</h2><p className="mt-2 max-w-2xl text-muted">Not cards: each has its own intake fields, evidence checklist, escalation ladder and knowledge coverage.</p>
          <ul className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{DOMAINS.map(([n, d, i]) => (<li key={n}><Tilt className="card h-full"><span className="grid h-10 w-10 place-items-center rounded-xl bg-teal-soft text-teal"><Icon name={i} size={20} /></span><h3 className="mt-3 font-bold">{n}</h3><p className="mt-1 text-sm text-muted">{d}</p></Tilt></li>))}</ul>
        </section>

        <section id="business" className="mx-auto mt-4 grid max-w-6xl scroll-mt-24 gap-4 px-4 pt-12 sm:px-6 md:grid-cols-2">
          <article className="card"><Tag tone="indigo">Computer & browser work</Tag><h3 className="mt-3 text-xl font-bold">“Follow up with Jordan Lee using the latest report.”</h3><p className="mt-2 text-muted">Two contacts share the name, so REDEEM refuses to guess. It picks the latest report by bytes, drives a real browser through your CRM and outbox, snapshots every step, and only sends what you approved — the exact report, to the exact person.</p></article>
          <article className="card"><Tag tone="teal">Business</Tag><h3 className="mt-3 text-xl font-bold">Shop call to confirmed reservation</h3><p className="mt-2 text-muted">A caller wants two keyboards for tomorrow. REDEEM picks the right customer record, reserves stock atomically (no overselling under concurrency), updates the CRM and reads the reservation back.</p></article>
        </section>

        <section className="mx-auto mt-4 max-w-6xl px-4 sm:px-6">
          <div className="card grid gap-6 md:grid-cols-2"><div><h2 className="text-2xl font-extrabold tracking-tight">Verified means checked, not claimed</h2>
            <p className="mt-2 text-muted">A provider saying “OK” is not proof. Lost acknowledgement? REDEEM looks it up before it ever retries. Page says “success”? It reads the system of record. You change your mind? Earlier approvals stop working.</p></div>
            <ul className="grid gap-2 text-sm">{[["USER PROVIDED", "what you said or approved"], ["PROVIDER CONFIRMED", "an acknowledgement, not proof"], ["DATABASE VERIFIED", "read back independently"], ["INFERRED", "REDEEM's rules, labelled as such"], ["UNVERIFIED", "stated plainly, never hidden"]].map(([k, v]) => <li key={k} className="flex flex-wrap items-center gap-2 rounded-xl bg-soft px-4 py-2.5"><Tag tone="indigo">{k}</Tag><span className="text-muted">{v}</span></li>)}</ul></div>
        </section>

        <section id="security" className="mx-auto mt-4 max-w-6xl scroll-mt-24 px-4 sm:px-6">
          <div className="card"><h2 className="text-2xl font-extrabold tracking-tight">Permission and privacy controls</h2>
            <ul className="mt-4 grid gap-3 text-sm sm:grid-cols-2">{["Nothing consequential runs without an approval bound to its exact target and amount", "Passwords, CAPTCHAs, one-time codes and payments are always yours; REDEEM pauses", "Every document and workspace is private to you; export or delete everything", "Callers are told they're speaking with an AI; recording is a separate opt-in", "Web pages and documents are data, never instructions", "Revoke any connection and its actions stop immediately"].map((x) => (<li key={x} className="flex gap-3"><span aria-hidden className="text-teal"><Icon name="check" size={16} /></span>{x}</li>))}</ul></div>
        </section>

        <section id="developers" className="mx-auto max-w-6xl scroll-mt-24 px-4 py-16 sm:px-6">
          <h2 className="text-2xl font-extrabold tracking-tight">What is real today</h2><p className="mt-2 text-muted">We list what works and what does not. There are no customer numbers or success rates because there are no customers yet.</p>
          <ul className="mt-6 divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">{REAL.map(([name, note, tone]) => (<li key={name} className="flex flex-col gap-1 px-5 py-4 sm:flex-row sm:items-center sm:justify-between"><div><p className="font-semibold">{name}</p><p className="text-sm text-muted">{note}</p></div><Tag tone={tone}>{tone === "teal" ? "Works (fixtures)" : tone === "amber" ? "Needs credentials" : "Not available"}</Tag></li>))}</ul>
        </section>

        <section className="relative overflow-hidden border-t border-line px-4 py-24 text-center sm:px-6"><Starfield /><h2 className="relative text-4xl font-extrabold tracking-tight sm:text-6xl"><span className="glow-text">{t("hero.title1")} {t("hero.title2")}</span></h2><Link href="/register" className="btn-primary relative mt-8">{t("nav.start")}</Link></section>
      </main>
      <footer className="border-t border-line px-4 py-8 text-sm text-muted sm:px-6"><div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3"><Logo /><button className="btn-ghost !min-h-[36px]" onClick={() => window.dispatchEvent(new Event("redeem:intro"))}>Replay intro</button><p>Built for the Bolna × YC Symphony Buildathon 2026. Not endorsed by Bolna or Y Combinator. Includes MIT-licensed code and data from RESOLVE and RECLAIM.</p></div></footer>
    </>
  );
}
