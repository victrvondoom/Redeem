# Open blockers
1. No Bolna credentials → every live-voice claim is UNVERIFIED. `POST /call` and `GET /executions/{id}` shapes unverified (docs host unreachable).
2. No Docker daemon → images never built; `docker compose config` parses.
3. Postgres never exercised (see MANUAL_ACTIONS_LATER M5).
4. No verified official regulatory corpus → no real legal citation can be produced.
5. No isolated browser runtime → cloud browser/computer-use is BLOCKED by design.
6. No LLM wired: routing/planning are deterministic rules.
7. Execution is synchronous in-request (no durable worker queue).
8. Not built: task-graph compiler with dependency scheduling, billing domain, developer sandbox, PDF extraction, email-draft connector, human-handoff state, Voice Quality Lab labelled intent/entity datasets, charts beyond the benchmark bars, CI deploy job.
