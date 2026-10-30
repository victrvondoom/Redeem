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


# Sprint 4 evidence (commands run in this sandbox)
| Check | Command | Result |
|---|---|---|
| Backend | `cd apps/api && python -m pytest -q` | **121 passed** |
| Lint (py) | `ruff check app` | clean |
| Types / build (web) | `npx tsc --noEmit`, `npx next build` | clean / compiled |
| Lint (web) | `npx eslint .` | 0 errors, 8 warnings (fetch-on-mount) |
| E2E | `PW_CHROMIUM_PATH=/opt/pw-browsers/chromium npx playwright test` | **20 passed** (incl. demo A/B/C, mission control, evidence download, connector honesty, first-use checklist, 390/360 overflow) |
| Migrations | `tests/test_migrations.py` (0001–0003, `alembic check`) | passed (SQLite only) |
| Perf | `python scripts/perf.py` | create+plan p50 33.1 / p95 43.7 ms; full approve→execute→verify p50 89.3 / p95 116.6 ms; 200 concurrent reads 56 req/s; in-process SQLite, not a load test |
| Visual QA | Playwright screenshot of the demo-A mission page at 1440px inspected (plan, alternatives, receipt, Evidence Center, agent activity render correctly); earlier sprint screenshots of other pages; overflow sweep covers all authenticated pages. **Known UX debt:** the ledger makes completed mission pages very long. |
| Competitor review | 14 repos cloned read-only and inspected | docs/COMPETITOR_TEARDOWN.md |

## Benchmark (seed 7, 7 scenarios x 30 = 210 trials per policy; local fixtures only)
| Policy | n | Correct | Verified | Wrong target | Duplicates | False success | Unauthorized |
|---|---|---|---|---|---|---|---|
| A naive | 210 | 0 | 0 | 30 | 60 | 210 | 90 |
| B checked | 210 | 60 | 60 | 30 | 0 | 150 | 90 |
| C redeem | 210 | 210 | 90 | 0 | 0 | 0 | 0 |
| C minus digest | 210 | 180 | 90 | 0 | 0 | 30 | 30 |
| C minus verifier | 210 | 150 | 90 | 0 | 0 | 60 | 30 |
| C minus reconcile | 210 | 210 | 60 | 0 | 0 | 0 | 0 |
New scenarios this sprint: revoked connector, cross-domain dependency failure. Finding: without the independent verifier a dependent task (family message) fires on a refund that never happened. REDEEM's 210/210 is on scenarios built around its own controls, so it is not evidence of production reliability. Entity-binding, temporal-guard and ledger ablations were not run.
