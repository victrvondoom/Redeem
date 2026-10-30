# Verification evidence (all commands run in this sandbox)
| Check | Command | Result |
|---|---|---|
| Backend | `cd apps/api && python -m pytest -q` | 90 passed |
| Lint (py) | `ruff check app` | clean |
| Types (web) | `cd apps/web && npx tsc --noEmit` | clean |
| Lint (web) | `npx eslint .` | 0 errors, 7 warnings (set-state-in-effect on fetch-on-mount, intentional) |
| Build | `npx next build` | compiled |
| E2E | `PW_CHROMIUM_PATH=/opt/pw-browsers/chromium npx playwright test` | 13 passed |
| Migrations | `tests/test_migrations.py` (upgrade head + `alembic check`) | passed (SQLite) |
| Benchmark | `python evals/runners/benchmark.py --n 30 --seed 7` | 900 trials, `evals/reports/benchmark_results.json` |
| Perf | `python scripts/perf.py` | `docs/PERF_RESULTS.json` (create+plan p50 26.8 ms / p95 33.8 ms; full approve→execute→verify p50 86.8 ms / p95 129.5 ms; 200 concurrent reads at 59 req/s; in-process SQLite, not a load test) |
| Visual QA | Playwright screenshots (1440 desktop Quality Lab, 390 mobile mission) inspected; overflow sweep: 9 authenticated pages × hi/ta/te × 1024/768/390/360 | no horizontal overflow |
| Compose | `docker compose config -q` | parses; **not built or run** |

## Benchmark (seed 7, 30 trials × 5 scenarios = 150 per policy; local fixture)
| Policy | Correct | Verified | Wrong target | Duplicates | False success | Unauthorized |
|---|---|---|---|---|---|---|
| A naive | 0 | 0 | 30 | 60 | 150 | 30 |
| B checked | 60 | 60 | 30 | 0 | 90 | 30 |
| C REDEEM | 150 | 90 | 0 | 0 | 0 | 0 |
| C − digest | 120 | 90 | 0 | 0 | 30 | 30 |
| C − verifier | 120 | 90 | 0 | 0 | 30 | 0 |
| C − reconcile | 150 | 60 | 0 | 0 | 0 | 0 |
REDEEM's scores come from scenarios designed around its own mechanisms; they are not evidence of production reliability. Entity-binding, temporal-guard and ledger ablations were **not** run.
