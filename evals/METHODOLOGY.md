# Benchmark methodology
- Command: `python evals/runners/benchmark.py --n 30 --seed 7` → `evals/reports/benchmark_results.json` (raw per-trial rows + summary).
- 5 scenarios × 3 policies × 30 trials = 450 trials, each on a fresh fixture tenant. Seeded; target booking order is randomised per trial.
- Ground truth is read from fixture tables (requests per booking), never from a policy's own report.
- Metric definitions: `correct_outcome` = exactly one refund request on the intended booking and none on the wrong one; for `stale_target` it means no effect and no success claim; for `silent_drop` (effect impossible) it means no success claim. `false_success` = reported full success while outcome incorrect. `PARTIALLY_VERIFIED` is not counted as success.
- Policies A (naive) and B (checked) are our own reference executors modelling stated capabilities. They are not other products; no competitor was run.
- Scope: local stateful fixture only. No live provider, no latency/cost claims (timings are in-process fixture timings). Not proof of general reliability.
- Not run: ablations of individual REDEEM mechanisms, adversarial web/transcript injection (covered by pytest, not scored here), cross-tenant attempts (pytest).
