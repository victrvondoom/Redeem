# Execution log
- S3 start: verified baseline (60 pytest / 6 E2E green).
- Added fixtures + connectors: calendar, CRM, case desk; migration 0002 (drift test caught it first).
- Added safety engine, citation validator, SSRF guard + browser gate, viewer role, workflows, voice tool endpoints, post-call analysis.
- Cross-domain mission (refund + hotel + calendar) in one mission; partial completion verified when one connector is revoked.
- Benchmark: 6 policies (A, B, C, C−digest, C−verifier, C−reconcile) × 5 scenarios × 30 seeds; first run exposed two metric-definition mistakes in my runner (documented in evals/METHODOLOGY.md).
- Perf script run (docs/PERF_RESULTS.json). It surfaced the duplicate-refund planning gap → fixed.
- UI: workflows page, benchmark + ablation table/bars, localised mission page, ESLint; 13 E2E incl. overflow sweep in hi/ta/te at 4 widths.
- Interrupted once by the user while starting a local Postgres; the instance was stopped and removed. Postgres remains unverified.

## Sprint 4
- Verified Sprint 3 baseline (90 pytest). Cloned and reviewed 14 competitor repos read-only; wrote COMPETITOR_TEARDOWN.md; learned Bolna contract corroboration (/call, /executions, two session endpoints) and that Bolna does not sign webhooks.
- Built: agent roles + capability matrix; task graph (dependencies, concurrent reads, comms drafts, alternatives); pause/resume/reject/escalate; observer escalation; Evidence Center + reports; connector manifests/health; demo scenarios A/B/C + reset; activation funnel; voice continuity tools + localized read-back + interrupt; provider interface, endpoint fallback, IP allowlist, circuit breaker; agent tool export; benchmark +2 scenarios.
- Test hygiene: found and fixed weak assertions of my own (`or True`), a missing view field (paused/escalated), and test-selector ambiguities.
- Docs: gap analysis, positioning, moat, YC narrative, competitive positioning, demo script, manual actions M13-M16.
