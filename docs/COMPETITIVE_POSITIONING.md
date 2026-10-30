# Competitive positioning (evidence: docs/COMPETITOR_TEARDOWN.md; README + selected source review of 14 repos)
| Capability | Best-in-set (observed) | REDEEM today |
|---|---|---|
| Live Bolna calls with honest status | Ruko (5 live calls, scripted customer) | **Behind** — none run |
| Deployed hosted app | Ruko, AI Sales Engineer, Dukan (links in READMEs) | **Behind** — local only |
| Prompt/guardrail red-team replay | Sentinel, Collections Agent | Partial (policy tests, benchmark) |
| Statistical rigor on judging | CallGrade (kappa, 95% CIs) | Behind (denominators yes, intervals no) |
| Provider drift monitoring | BolnaMonitor | Not built |
| Single-domain depth | Ruko (payments), Dukan (retail), Saathi (pharma) | Shallower per domain |
| **Cross-domain mission with dependencies** | none of the 14 present this as their use case (README review) | **Implemented, fixture-verified** |
| **Independent effect read-back + reconcile-not-resend + approval digest** | partial ideas: Ruko re-reads executions; wareongo reconciles batches | **Implemented across all connectors, tested, ablated** |
| Evidence categories (user / provider / DB-verified / inferred / unverified) | not observed | Implemented |
Do **not** claim superiority over these repos: no head-to-head test under comparable conditions was run, and several are ahead on live validation.
