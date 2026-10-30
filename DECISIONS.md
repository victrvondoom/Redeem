# Decisions
- SQLite default; Postgres via REDEEM_DATABASE_URL (untested). Alembic migrations not generated yet (create_all).
- No Redis/worker yet: execution is synchronous in-request with a write-ahead ledger and startup recovery.
- Rule-based language detection and domain routing (deterministic). No LLM wired in yet.
- Idempotency key is stable per logical operation across revisions; Action uniqueness is per revision.
- Approvals bind to sha256(mission, tenant, revision, action, target, params, amount, target version hash) + expiry; re-verified at dispatch.
- Webhooks: Bolna signing not assumed. Shared-secret token + read-back from Bolna; webhooks only update call bookkeeping.
- Session-mint contract is from the published @bolna/web-call@3.0.1 README. POST /call and GET /executions/{id} are unverified against live docs (docs.bolna.ai unreachable from the build sandbox).
- Same-origin Next.js rewrite keeps the session cookie HttpOnly and first-party.
