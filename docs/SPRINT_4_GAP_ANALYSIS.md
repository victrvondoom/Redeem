# Sprint 4 gap analysis (start of sprint; verified, not trusted)
Baseline re-run: branch `claude/peaceful-turing-xnfcuc` @ `ad7b31f`; 90 pytest, 13 Playwright, ruff/tsc/build green.

**Functional (verified):** auth/CSRF/tenancy; deterministic mission state machine; digest-bound approvals; ledger with hash-chained receipts; reconcile-not-resend; restart recovery; 6 fixture connectors incl. calendar/CRM/case desk; safety engine; benchmark with 3 ablations; Bolna adapter (mock-tested).
**Incomplete:** orchestration was one linear action list — no dependencies, no concurrent reads; "agents" existed only as comments, not as enforced roles; no pause/reject/escalate; no per-mission evidence model; connectors had no manifest/health; Quality Lab lacked revoked-connector and dependency-failure cases; no demo reset/repeatability; no activation tracking.
**Fixture-only / fake-adjacent:** every external effect (airline, hotel, calendar, shop, CRM, case desk) is a local stateful fixture — now labelled in UI/receipts; messages are drafts (nothing sent); regulatory sources are fixtures.
**Missing integrations:** live Bolna, OAuth calendar/email, real CRM, official regulatory corpus, isolated browser. (All in MANUAL_ACTIONS_LATER.)
**Broken journeys found:** a replan/mission on an already-refunded booking (fixed in Sprint 3); voice follow-ups had no way to resolve "the second option" (fixed now).
**Competitor gaps:** see COMPETITOR_TEARDOWN.md.
**Debt:** synchronous execution (no durable worker/outbox), process-local rate limiter and circuit breaker, SQLite-only verification, rule-based routing (no LLM), 8 ESLint warnings (fetch-on-mount).
