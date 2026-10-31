# Open blockers
1. No Bolna credentials → every live-voice claim is UNVERIFIED. `POST /call` and `GET /executions/{id}` shapes unverified (docs host unreachable).
2. No Docker daemon → images never built; `docker compose config` parses.
3. Postgres 16 verified locally (migrations, no drift, full backend suite 199 passed); the Docker build/compose path is still untested (MANUAL_ACTIONS_LATER M5).
4. No verified official regulatory corpus → no real legal citation can be produced.
5. No isolated browser runtime → cloud browser/computer-use is BLOCKED by design.
6. No LLM wired: routing/planning are deterministic rules.
7. Execution is synchronous in-request (no durable worker queue).
8. Not built: task-graph compiler with dependency scheduling, billing domain, developer sandbox, PDF extraction, email-draft connector, human-handoff state, Voice Quality Lab labelled intent/entity datasets, charts beyond the benchmark bars, CI deploy job.

## Added in Sprint 4
9. Durable background jobs, outbox, dead-letter queue, execution leases, distributed tracing: **not built** (execution is synchronous; see DECISIONS.md). Justification: no long-running provider work exists until live connectors do.
10. Circuit breaker and rate limiter are process-local (single instance only).
11. Voice: no live-call evidence of interruption handling, language switching, or tool calls; agent definition export is unverified against a live Bolna account.
12. Quality Lab has no latency/cost-per-verified-mission from live data (fixture timings only).
13. Competitor repos were reviewed at source level but their deployed apps were not exercised.
5. Official partner logos: Bolna and Wispr Flow are now embedded (downloaded unmodified from their own sites on 2026-10-31). Y Combinator and WeMakeDevs SVGs are still absent; logos must not be redrawn. Place official files in apps/web/public/brand/ (see its README); the intro cubes pick them up automatically.
6. No KMS: the key-encryption key comes from REDEEM_MASTER_KEY. Production must set it (REDEEM_ENV=production refuses to start without it).

14. Browser skill run control (pause/resume/stop) lives in process memory: with more than one API instance, a control request must reach the instance running the skill. Runs execute in a daemon thread; a restart mid-run leaves the row RUNNING (not yet reconciled at startup).
