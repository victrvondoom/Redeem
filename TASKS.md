# Tasks
- [ ] Live Bolna web call verified (execution id correlated; webhook read-back advances status)
- [x] Alembic initial migration (SQLite)
- [ ] Postgres test run
- [x] evals/ 3-policy benchmark with raw JSON
- [x] evals/ ablations (digest, verifier, reconcile)
- [ ] injection/cross-tenant scoring in benchmark
- [x] Calendar connector for cross-domain mission
- [x] Task-graph with dependency scheduling
- [ ] Remaining ablations: entity binding, temporal guard, ledger
- [ ] Billing + developer domains; email draft connector; PDF extraction; human-handoff state
- [ ] Docker Compose + deployment config
- [ ] Native review of hi/ta/te copy; localise detail screens
- [ ] Durable worker for long-running execution
- [ ] Verified legal-source corpus before any citation
- [ ] Demo script, submission text, README diagrams

## Sprint 4 remaining
- [ ] Live Bolna exercise (M1/M2/M13) → upgrade condition to LIVE_VERIFIED only with evidence
- [ ] Durable worker + outbox + DLQ + leases (when live connectors exist)
- [ ] Judge calibration + confidence intervals in Quality Lab (CallGrade-style)
- [ ] Provider drift monitoring from Bolna meta_info (BolnaMonitor-style)
- [ ] Collections/billing domain with consent + DNC state
- [ ] Spend guards (daily cap / wallet floor)
- [ ] Entity-binding / temporal-guard / ledger ablations
- [ ] Deploy + record demo (M7, M12)
