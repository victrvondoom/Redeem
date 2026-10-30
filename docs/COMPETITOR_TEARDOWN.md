# Competitor teardown (source-level, 30 Oct 2026)
**Method.** All 14 repositories exist and were cloned read-only (shallow, depth 1) into an isolated scratch directory. I did **not** run any of their code. For each I read the README and inspected the file tree, manifests, test files, Bolna API usage and reliability-related keywords (`grep` counts are noted as *observed counts*, not quality judgements). I read selected source files for Ruko, Dukan, Sentinel, wareongo and callgrade; for the rest the README and tree only. Nothing was copied. **Observed** = seen in the repo. **Inferred** = my reading; marked as such. I did not use the apps' live deployments.

**Participation:** only the repos' own READMEs can tell. Mentions of "Symphony/buildathon": Ruko (30 files), Convox (27), Setu (6), Sentinel (1); the other ten mention neither. Independent confirmation of participation was **not** possible from here for any of them. `symphony_bolna` contains **zero** references to Bolna (observed), despite its name.

| Repo | Last commit | Stack (observed) | Tests (files) | Bolna refs (files) |
|---|---|---|---|---|
| Ruko | 2026-10-23 | TypeScript, React, own ML lexicon model | 16 | 130 |
| Sentinel | 2026-10-28 | Python API + Next.js | 4 | 44 |
| Dukan | 2026-06-01 | Next.js, Supabase | 0 | 43 |
| AI Sales Engineer | 2026-10-30 | React/Vite, Express, Supabase | 18 | 49 |
| CallGrade | 2026-10-28 | Python (anthropic/openai SDKs), static demo | 7 | 8 |
| BolnaMonitor | 2026-07-03 | FastAPI, 13 files | 0 | 8 |
| Saathi | 2026-10-29 | FastAPI + SQLAlchemy, Next.js 16 | 4 | 21 |
| Collections Agent | 2026-09-12 | Prompt/config + docs only (13 files) | 0 | 3 |
| Convox | 2026-10-27 | Python (260 files) | 135 | 13 |
| CRM–Twilio (NexaCRM) | 2026-10-27 | Java Spring Boot + React + MongoDB | 0 | 18 |
| WareOnGo | 2026-10-30 | Next.js, Prisma, OpenAI | 16 | 70 |
| n8n Bolna nodes | 2026-08-04 | TypeScript n8n node | 0 | 7 |
| symphony_bolna (Vantari) | 2026-10-27 | TypeScript backend | 23 | **0** |
| Setu | 2026-10-27 | Next.js 14, Supabase, Twilio, Groq | 0 | 17 |

## Per-repository findings
**Ruko — payment-scam prevention (strongest rival).** *Purpose:* hold a coached payment, then a Bolna agent calls the customer in their language; code word proves the call is genuine; deterministic policy decides release/delay/block. *Observed:* public README with a "Status, honestly" note — five live Bolna web calls were run (23 Oct; four English, one Hindi), always with a scripted TTS "customer", not a real person; three Bolna agents built from code (`bolna:setup`), custom functions (`get_check_context`, `record_signal`, `set_decision`…), session minting behind access code + daily cap + wallet floor read from `GET /user/me`, webhooks gated by URL token + optional IP allowlist + **re-read of terminal events from Bolna**, idempotent per (execution, status); `server/engine/policy.ts` and `decision.ts` are deterministic; a fraud-ops console, a public "Is this a scam?" checker, research/business/citation docs, deck, demo script, hosted app. *Strengths:* verified live voice, honest status, cited statistics, deployed. *Weaknesses (evidence-based):* single domain (payments); its own README says mid-call language switching is "not yet tried" and the customer in all live calls was scripted. *REDEEM can do better:* general execution across domains with independent state read-back. *REDEEM is behind on:* live Bolna verification, deployment, agent-as-code setup (partly addressed: `app/voice/agent_config.py`), spend guards (wallet floor/daily cap).

**Sentinel — voice-agent testing/auditing.** *Observed:* offline "Rehearsal" mode needing no keys, replay/comparison of guardrail changes, recording credential isolation tests, 48 backend + 7 browser tests recorded in `docs/VERIFICATION.md`, one real external-model smoke test (Groq) recorded separately, Render deployment blocked at `need_payment_info`. Domain: lending/customer support, English + Hindi. *Strength:* test-before-ship workflow for prompts. *Weakness:* tests the *agent's conversation and tool decisions*, not whether the external effect happened (**inferred** from README scope). *REDEEM:* its Quality Lab measures effect verification; it lacks Sentinel's prompt-level red-team replay UI.

**Dukan — Hindi/English kirana ordering.** *Observed:* Next.js + Supabase; five agent tool endpoints with real DB logic; README phase table says Bolna agent build and merchant dashboard pages are still "next"; **0 test files**; comment states "Bolna does not sign webhooks… source IP allowlist (13.203.39.153)". *Weakness:* unfinished and untested per its own status table. *REDEEM:* retail reservation with atomic stock, tests, verification.

**AI Sales Engineer (AsterByte).** *Observed:* live site, Bolna browser calls (`/web-call/session`, `/executions/`), Sarvam ASR + Gemini + TTS pipeline, Supabase tickets/enquiries/consultations, Google Calendar + Meet creation, admin dashboard, 18 test files. *Strength:* a polished single-company sales/support flow with real calendar creation. *Weakness:* one business, one fictional account (**inferred** from README). *REDEEM:* cross-domain missions; it lacks real calendar/OAuth (blocked on credentials).

**CallGrade — call-quality grading.** *Observed:* grades calls from any platform with 3 judges, quadratic-weighted kappa, 95% intervals, held-out set (14 calls: 6 clean, 8 planted), deliberately admits small-n uncertainty. *Strength:* the best statistical honesty in the set. *REDEEM:* its Quality Lab reports denominators and caveats but has no judge-calibration; adopting interval reporting is a todo.

**BolnaMonitor — provider drift detection.** *Observed:* 13 files, z-score/error-rate/threshold alerts on per-turn latency from Bolna `meta_info`; no tests. *REDEEM:* shows "Not measured" for latency; ingesting `meta_info` is possible once live calls exist (todo).

**Saathi — pharma field-rep voice debrief/briefing.** *Observed:* multi-tenant FastAPI + Next.js; Bolna asks `GET /bolna/caller` before the call and custom functions run mid-call; misheard names are checked against company lists; 4 test files. *REDEEM:* healthcare administration is a case-desk preparation slice only; no field-visit workflow.

**Collections Agent — Hinglish EMI collections, red-team first.** *Observed:* prompt/config + `RESULTS.md`: five adversarial cases run against the deployed agent incl. do-not-call and no-consequence statements, tool calls verified at a webhook catcher. 13 files, no code tests. *Strength:* compliance-ranked guardrails. *REDEEM:* billing/collections domain is **not built**; its safety engine refuses unsafe intents but has no consent/DNC state.

**Convox — live phone interpreter.** *Observed:* 260 Python files, 135 test files, STT→translate→TTS with ~1.5 s latency claim, Indian-language focus. *Different problem* (interpretation); little overlap. (**Inferred:** its latency figure is the README's claim, not measured by me.)

**CRM–Twilio (NexaCRM).** *Observed:* Java Spring Boot CRM with AI scoring, Kanban, automation, optional Bolna auto-call; 0 tests. *REDEEM:* thinner CRM but verified state changes.

**WareOnGo — warehouse sourcing calls.** *Observed:* Bolna batches (`/batches`, schedule), execution reconciliation code with retry classification, terminal-status handling, transcript analysis via OpenAI, human verification channel, 16 tests. *Strength:* real operational batch reconciliation — closest in spirit to REDEEM's reconcile idea. *REDEEM:* reconciles side effects, not call batches.

**n8n Bolna nodes.** *Observed:* thin wrapper over `/call`, `/executions`, `/v2/agent/*`; no tests. Useful as an interface reference only.

**symphony_bolna (Vantari) — family health agent.** *Observed:* backend-first TypeScript, 23 tests, explicit "never diagnoses/dose/condition" rule, wallet/booking/transport concepts; **no Bolna code**. *Inferred:* voice is planned elsewhere. Strong safety framing, same as REDEEM's administrative-only stance.

**Setu — elderly phone caregiver.** *Observed:* Bolna session + `/call` (note: some calls use `api.bolna.dev`, others `.ai`), Twilio SMS, Supabase, Groq transcript analysis, Hindi; no tests. *REDEEM:* no elder-care flow.

## What the teardown changed in REDEEM (done this sprint)
1. **Bolna contracts corroborated:** `POST /call` and `GET /executions/{id}` are used identically by several independent projects; web-call minting is `/web-call/freeswitch-session` (SDK) vs `/web-call/session` (docs) — REDEEM now falls back between them. Still **not live-verified by me**.
2. **Webhook authenticity:** two projects state Bolna does not sign webhooks and rely on source IPs; REDEEM already used token + read-back and now has an optional IP allowlist (`BOLNA_WEBHOOK_ALLOWED_IPS`). I did not hard-code any IP.
3. **Agent-as-code:** exportable tool definitions + safety prompt (`python -m app.voice.agent_config`).
4. **Circuit breaker** for provider failures.
## Not matched (honest)
Live Bolna calls and a deployed app (Ruko), prompt red-team replay UI (Sentinel), judge calibration/intervals (CallGrade), drift alerts (BolnaMonitor), real calendar/OAuth (AI Sales Engineer), spend guards (Ruko), compliant collections flows (Collections Agent).
