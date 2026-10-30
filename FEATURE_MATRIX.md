# Feature matrix (truthful)
| Feature | Status | Evidence |
|---|---|---|
| Auth, sessions, CSRF, rate limit, tenant isolation | LOCALLY_TESTED | apps/api/tests/test_auth_tenancy.py |
| Mission state machine, digest approvals, ledger, receipts | LOCALLY_TESTED | tests/test_flight_mission.py |
| Flight-refund mission (fixture) | END_TO_END_VERIFIED (fixture only) | pytest + Playwright |
| Retail reservation + CRM stage (fixture) | END_TO_END_VERIFIED (fixture only) | pytest + Playwright |
| Intent correction, approval invalidation, stale-exec abort | LOCALLY_TESTED | pytest |
| Ack-loss reconcile, silent-drop detection, restart recovery | LOCALLY_TESTED | pytest + Playwright |
| Bolna session mint, webhook, call ledger | LOCALLY_TESTED (mock transport) | tests/test_voice_bolna.py; no live call made |
| Bolna outbound + execution read-back | IMPLEMENTING (contract unverified) | mock only |
| Multilingual UI en/hi/hinglish/ta/te | LOCALLY_TESTED; no native review; detail screens mostly English | Playwright |
| Live voice quality per language | BLOCKED (needs Bolna credentials) | — |
| Payment-safety scanner | LOCALLY_TESTED (heuristic) | tests |
| Seeded policy benchmark (3 policies × 5 scenarios × 30 trials, raw JSON) | LOCALLY_TESTED (fixture only; REDEEM 150/150 on its own designed scenarios, so not evidence of general reliability) | evals/runners/benchmark.py, evals/METHODOLOGY.md, tests/test_benchmark.py |
| Alembic initial migration (SQLite) | LOCALLY_TESTED (drift check) | tests/test_migrations.py |
| Dockerfiles + compose (Postgres) | IMPLEMENTING — untested, no Docker daemon in sandbox | — |
| Cross-domain mission (flight + hotel + calendar) | PARTIAL: flight + hotel in one mission; calendar not built | — |
| Legal citations, PDF parsing, workflow builder, benchmark ablations, background worker, tool/function calling, post-call analysis, other domains, web lint, cloud-browser isolation | IDEA/SPECIFIED — not built | — |
| Deployment | not done | — |

## Sprint 3 additions
| Feature | Status | Evidence |
|---|---|---|
| Cross-domain mission: refund + hotel + calendar, partial completion | END_TO_END_VERIFIED (fixture) | tests/test_domains_expansion.py, E2E |
| CRM follow-up (same-name contacts, stale record, readback) | END_TO_END_VERIFIED (fixture) | pytest |
| Case preparation: telecom, housing, government, healthcare billing, insurance, e-commerce | LOCALLY_TESTED — creates a verified *internal* case record; nothing filed externally; only fixture sources | pytest |
| Safety engine (credential/clinical/transfer refusals, scam warning, injection, per-action policy events) | LOCALLY_TESTED | pytest |
| Citation validator (forged citation rejected) | LOCALLY_TESTED; no official corpus ingested | pytest |
| Atomic inventory + concurrency test | LOCALLY_TESTED (SQLite) | pytest |
| Mandatory ack-lost → restart → reconcile; provider-cannot-reveal → UNCERTAIN | LOCALLY_TESTED | pytest |
| Viewer role read-only | LOCALLY_TESTED | pytest |
| Workflow library (9 workflows) | LOCALLY_TESTED | pytest, E2E |
| Bolna function-tool endpoints + post-call analysis | LOCALLY_TESTED (mock) — LIVE: UNCONFIGURED | tests/test_voice_bolna.py |
| SSRF guard; cloud browser | guard LOCALLY_TESTED; browser BLOCKED (no isolation) | pytest |
| Benchmark ablations (3 of 6 requested controls) | LOCALLY_TESTED | evals/ |
| Perf measurements | MEASURED (in-process) | docs/PERF_RESULTS.json |
| Web lint | PASS (0 errors, 7 warnings) | eslint |
| Task-graph compiler with dependency scheduling | NOT BUILT | — |
| Billing, developer automation, email drafts, PDF extraction, human-handoff state | NOT BUILT | — |

## Sprint 4 additions (all fixture-level unless stated; nothing LIVE_VERIFIED)
| Feature | Status | Evidence |
|---|---|---|
| Agent roles with capability matrix (only executor dispatches; recovery lookup-only) + observable AGENT events | LOCALLY_TESTED | tests/test_sprint4.py |
| Task-graph: dependency-gated writes, SKIPPED_DEPENDENCY, concurrent read-only tasks | LOCALLY_TESTED | pytest |
| Mid-execution correction preserves completed work, voids stale approvals | LOCALLY_TESTED | pytest |
| Mission control: pause / resume / reject / escalate (+ observer auto-escalation on contradictory evidence) | LOCALLY_TESTED + E2E | pytest, Playwright |
| Evidence Center (5 trust categories, content hashes, JSON + Markdown report) | LOCALLY_TESTED + E2E | pytest, Playwright |
| Connector manifests + health (UNCONFIGURED / FIXTURE_VERIFIED; none LIVE_VERIFIED) | LOCALLY_TESTED + E2E | pytest, Playwright |
| Communication drafts (comms fixture; nothing sent) | LOCALLY_TESTED | pytest |
| Demo scenarios A/B/C with reset, repeatable | LOCALLY_TESTED + E2E | pytest, Playwright |
| Voice continuity tools: mission_reply (ordinal/reference resolution), read_back_plan (5 languages, cannot approve), interrupt | LOCALLY_TESTED (mock) — LIVE: UNCONFIGURED | tests |
| Provider-independent voice interface; Bolna session-endpoint fallback; webhook IP allowlist; circuit breaker | LOCALLY_TESTED (mock) | tests |
| Exportable Bolna agent tool definitions | IMPLEMENTED — UNVERIFIED against live Bolna | tests (shape only) |
| Activation funnel from real events + first-use checklist | LOCALLY_TESTED + E2E | pytest, Playwright |
| Benchmark: +revoked connector, +cross-domain dependency failure (7 scenarios) | LOCALLY_TESTED | evals/ |
| Competitor teardown (14 repos, source-level) | DONE | docs/COMPETITOR_TEARDOWN.md |
| NOT built: durable worker/outbox/DLQ/leases, tracing, entity-binding/temporal/ledger ablations, drift monitoring, judge calibration, collections/billing, deployment | — | docs/OPEN_BLOCKERS.md |
