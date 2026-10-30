# Sprint 3 baseline (measured at start of session)
Branch `claude/peaceful-turing-xnfcuc`, commit `338f9b7`, clean tree, remote `origin` writable.

**Working:** 60 pytest, ruff, tsc, production build, 6 Playwright — all passing. Flight and shop missions on fixtures; Bolna adapter mock-tested.
**Incomplete at start:** no calendar/CRM/case-desk domains; domains other than travel/retail/banking-scan were registry text only; no tool-calling; no post-call analysis; no ablations; no web lint; no perf measurement.
**Broken / gaps found during the sprint:**
- A second mission on an already-refunded booking planned a duplicate refund (caught by the verifier, but the planner should refuse) → fixed + test.
- Retail reservation decremented stock with a read-modify-write; fixed with an atomic conditional UPDATE + `CHECK(stock>=0)` + 8-thread test.
- ESLint absent; TypeScript 7 incompatible with typescript-eslint → pinned TS 5.9.
**Missing tests:** concurrency, migration drift, ablations, tool endpoints, SSRF, safety engine, viewer role.
**Security findings:** no read-only role enforcement (fixed: `viewer` → 403 on mutations); SSRF guard absent (added, not yet used by any fetcher because no URL-fetching feature exists); registration rate limit not configurable for E2E (added setting).
**Failing commands at start:** none.
**First priority:** unify domains behind the existing engine rather than adding parallel orchestrators.
