#!/usr/bin/env python3
"""Build docs/system-design/index.html — the visual system-design trail (20 topics) with an honest
audit of what REDEEM actually implements. Edit TOPICS below, then run:  python scripts/build_system_design.py
Status vocabulary (never upgrade without evidence in code/tests): IMPLEMENTED | PARTIAL | NOT IMPLEMENTED."""
from __future__ import annotations
import html
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "docs" / "system-design" / "index.html"

# kind: n=node  a=accent(the thing the topic is about)  bad=failure  ok=success
# a diagram is rows of (label, kind); consecutive boxes in a row are linked by arrows; rows are linked downward.
TOPICS = [
 dict(n="01", t="Rate Limiting", problem="One bot sends 10,000 req/s and starves everyone else.",
  how="Count requests per key (IP or user) in a time window. Over the limit -> HTTP 429 plus Retry-After. Token bucket refills at a steady rate.",
  diagram=[[("Bot / client", "n"), ("Edge limiter", "a"), ("App server", "n")], [("429 + Retry-After", "bad")]],
  take="Limit at the edge (gateway/CDN), not in app code; always tell the client when to retry.",
  status="PARTIAL", evidence="app/core/security.py RateLimiter: sliding window per user/IP on login, register, missions, voice, cases, benchmark; 429 now returns Retry-After + retry_after_seconds (tests/test_auth_tenancy.py). Gap: process-local memory, not Redis/edge, so limits are per-instance (noted in DECISIONS.md)."),
 dict(n="02", t="Caching", problem="Identical expensive queries hammer the database.",
  how="Cache-aside: check cache, on a miss read the DB, write the result back with a TTL.",
  diagram=[[("API", "n"), ("Cache (TTL)", "a"), ("Database", "n")], [("miss -> query -> store", "ok")]],
  take="Cache only read-heavy, rarely-changing, expensive data. Always set a TTL. Never put sessions on a public CDN.",
  status="NOT IMPLEMENTED", evidence="No application cache layer. Only HTTP hints exist: Cache-Control private,max-age=60 on screenshots and no-store on the SSE stream (app/api/ops.py, app/api/missions.py). Tenant-scoped data is deliberately read live."),
 dict(n="03", t="Load Balancing", problem="One server is a capacity limit and a single point of failure.",
  how="A balancer spreads requests (round robin) and health-checks nodes; a dead node stops receiving traffic.",
  diagram=[[("Clients", "n"), ("Load balancer", "a")], [("Node 1 ok", "ok"), ("Node 2 down", "bad"), ("Node 3 ok", "ok")]],
  take="Run >=2 instances behind a balancer with health checks before you need it.",
  status="NOT IMPLEMENTED", evidence="docker-compose.yml runs one api and one web container; no balancer. GET /health exists (app/api/misc.py) for a platform balancer to probe."),
 dict(n="04", t="Reverse Proxy", problem="App servers should not face the internet directly.",
  how="A proxy terminates TLS, compresses, serves static files and shields the backend.",
  diagram=[[("Internet", "n"), ("Nginx / Caddy (TLS)", "a"), ("App", "n")]],
  take="Never expose Express/Django/Uvicorn on 80/443 directly.",
  status="PARTIAL", evidence="Next.js proxies /api to the API in compose (REDEEM_API_URL) and the API sets nosniff / no-referrer headers and X-Accel-Buffering for SSE. No TLS-terminating proxy is shipped; deployment is not configured."),
 dict(n="05", t="API Gateway", problem="Many services means many URLs and auth checks per client.",
  how="One entry point verifies the token once, rate-limits, routes, and forwards the identity downstream.",
  diagram=[[("Mobile / Web", "n"), ("Gateway: auth + limit", "a")], [("User svc", "n"), ("Billing svc", "n"), ("Search svc", "n")]],
  take="Validate the token once at the edge; pass the user id downstream.",
  status="PARTIAL", evidence="Single FastAPI service: session auth is validated once in a shared dependency and tenant_id comes only from the session (AGENTS.md rule 4; IDOR tests per resource). It is a modular monolith, so no separate gateway is needed or built."),
 dict(n="06", t="CI/CD", problem="It works on my machine, then breaks in production.",
  how="Every push builds and tests automatically; only green builds may be deployed.",
  diagram=[[("Push", "n"), ("Build", "ok"), ("Test", "a"), ("Deploy", "n")], [("Test fails -> deploy skipped", "bad")]],
  take="AI-generated code never reaches users without a pipeline that runs tests and the build.",
  status="PARTIAL", evidence=".github/workflows/ci.yml runs sync_readme --check, ruff, pytest (api) and tsc, eslint, next build (web). CI only: there is no CD / deploy step."),
 dict(n="07", t="Docker", problem="Different OS and dependency versions behave differently.",
  how="Package code and dependencies into an image; run identical containers anywhere (shared kernel, lightweight).",
  diagram=[[("Dockerfile", "n"), ("Image", "a"), ("Container x N", "ok")]],
  take="Multi-stage build, small final image, run as non-root.",
  status="PARTIAL", evidence="apps/api/Dockerfile, apps/web/Dockerfile and docker-compose.yml (Postgres 16 + api + web) exist. The Docker build itself is untested: no Docker daemon in the build sandbox (AGENTS.md honest limits). Postgres 16 path was verified without Docker."),
 dict(n="08", t="Kubernetes", problem="Who restarts crashed containers across many machines?",
  how="You declare the desired state (3 replicas); the control plane keeps reality equal to it and self-heals.",
  diagram=[[("Control plane", "a")], [("Pod A", "ok"), ("Pod B crash", "bad"), ("Pod B restarted", "ok")]],
  take="Do not adopt Kubernetes for an MVP. Use a PaaS until you have many services and an operator.",
  status="NOT IMPLEMENTED", evidence="Intentionally absent; the guide itself advises against it at this stage."),
 dict(n="09", t="Service Discovery", problem="Container IPs change constantly.",
  how="Internal DNS maps a stable name (auth-service) to the current healthy instances.",
  diagram=[[("Service A", "n"), ("DNS: auth-service", "a"), ("Current IP", "ok")]],
  take="Address services by name, never by IP.",
  status="PARTIAL", evidence="Only docker-compose DNS names (api, db) are used. No dynamic discovery; there is one service."),
 dict(n="10", t="Circuit Breaker", problem="A slow dependency drags its callers down with it (cascading failure).",
  how="After N consecutive failures the breaker opens and fails fast; after a cooldown it lets one probe through (half-open).",
  diagram=[[("Service A", "n"), ("Breaker OPEN", "bad"), ("Service B down", "n")], [("instant fast-fail", "ok")]],
  take="Degrade gracefully: return an empty list for non-critical features instead of crashing.",
  status="IMPLEMENTED", evidence="app/voice/bolna.py CircuitBreaker (threshold 3, 30 s cooldown, half-open probe) guards the Bolna client and returns provider_circuit_open (503). Scope: the voice provider only; the Google adapter has none."),
 dict(n="11", t="Timeouts", problem="Waiting forever piles up connections and memory.",
  how="Every outbound call has a hard deadline; on expiry drop it and return an error.",
  diagram=[[("Call B", "n"), ("2 s deadline", "a"), ("Error to user", "bad")]],
  take="No call without a timeout.",
  status="PARTIAL", evidence="Each persisted mission task has timeout_ms (default 10000) and a retry_budget (app/orchestration/taskgraph.py); the browser runner and provider clients take timeouts from config. Not audited as universal: new outbound calls must set one."),
 dict(n="12", t="Retries", problem="Transient faults (503, timeout) should not fail the user.",
  how="Retry only transient errors, never 4xx; cap attempts.",
  diagram=[[("503", "bad"), ("retry", "a"), ("503", "bad"), ("retry", "a"), ("200", "ok")]],
  take="Max ~3 attempts, only on 5xx/timeouts, and only if the operation is idempotent.",
  status="PARTIAL", evidence="Read-only tasks carry a retry_budget; reconcile_action does up to 3 read-only lookups (engine.py). Writes are never auto-resent: an uncertain outcome is looked up, else sent to human review (AGENTS.md rule 5)."),
 dict(n="13", t="Exponential Backoff + Jitter", problem="Immediate retries from many clients become a self-inflicted DDoS.",
  how="Wait 1 s, 2 s, 4 s ... plus random jitter so clients do not retry in lockstep.",
  diagram=[[("fail", "bad"), ("wait 1s", "n"), ("fail", "bad"), ("wait 2s+jitter", "a"), ("ok", "ok")]],
  take="Backoff without jitter still synchronises clients.",
  status="NOT IMPLEMENTED", evidence="No backoff or jitter anywhere; reconcile_action states its backoff is a no-op for the in-process fixture. Needed before any real provider is called in anger."),
 dict(n="14", t="Idempotency", problem="A retry after a dropped reply charges twice.",
  how="Client sends an Idempotency-Key; the server remembers it and returns the stored result instead of redoing the work.",
  diagram=[[("POST key=xyz", "n"), ("Seen key?", "a")], [("yes: stored result", "ok"), ("no: run + store", "n")]],
  take="Keys on every endpoint that moves money, sends email, or creates data.",
  status="IMPLEMENTED", evidence="engine.py op_key() derives a deterministic idempotency_key per action; ProviderOperation rows record dispatches; verified actions are reused across revisions (ACTION_REUSED); reconcile-not-resend and restart recovery (recover_incomplete) are covered by the backend tests."),
 dict(n="15", t="Queues + Dead Letter Queue", problem="Heavy work makes the user stare at a spinner.",
  how="The web tier enqueues a job and replies at once; workers drain the queue; jobs that keep failing park in a DLQ for inspection.",
  diagram=[[("Web", "n"), ("Queue", "a"), ("Worker", "n")], [("fails 3x -> DLQ", "bad")]],
  take="Queues are for async background work, not normal reads/writes.",
  status="NOT IMPLEMENTED", evidence="Execution is synchronous (AGENTS.md honest limits). The nearest analogue is escalation to human review for stuck actions; there is no queue, worker or DLQ. Next step recorded in IMPLEMENTATION_STATE.md: durable worker/outbox."),
 dict(n="16", t="Pub/Sub", problem="Order service calling four systems directly is tightly coupled.",
  how="Publisher emits to a topic; any number of subscribers react independently and catch up after downtime.",
  diagram=[[("Order svc", "n"), ("Topic order_created", "a")], [("Inventory", "n"), ("Billing", "n"), ("Analytics", "n")]],
  take="Add a new consumer without touching the publisher.",
  status="NOT IMPLEMENTED", evidence="No broker. Missions append events to a per-mission ledger and /missions/{id}/stream serves them over SSE, which is a read stream for the UI, not inter-service pub/sub."),
 dict(n="17", t="Event-Driven Architecture", problem="Synchronous command chains break easily as systems grow.",
  how="Services broadcast immutable past-tense facts; others react. Needs distributed tracing (trace_id) to debug.",
  diagram=[[("UserCreated", "a"), ("Event bus", "n"), ("Email", "n"), ("Analytics", "n")]],
  take="Name events in the past tense; carry a trace id.",
  status="PARTIAL", evidence="Append-only, sequenced ledger of past-tense events per mission (e.g. ACTION_REUSED, RECONCILED_FOUND); X-Request-ID correlation id in every error body (app/main.py). No bus, no cross-service tracing: it is one service."),
 dict(n="18", t="Distributed Transactions", problem="A SQL transaction cannot span two databases.",
  how="Two-phase commit coordinates a commit across databases but is slow and holds locks.",
  diagram=[[("Billing DB -$50", "ok"), ("Rewards DB crash", "bad")], [("data now inconsistent", "bad")]],
  take="Avoid them: design so one transaction touches one database.",
  status="IMPLEMENTED", evidence="Avoided by design: one relational database, one transaction per state change. External systems are handled through connectors with idempotency + verify instead of 2PC."),
 dict(n="19", t="Saga Pattern", problem="Multi-step work across services needs undo when a step fails.",
  how="Chain local transactions; on failure run compensating transactions backwards. Accept eventual consistency and show 'Processing' states.",
  diagram=[[("1 Order", "ok"), ("2 Charge", "ok"), ("3 Ship fails", "bad")], [("undo charge", "a"), ("cancel order", "a")]],
  take="Design the UI for in-between states, not just Done.",
  status="PARTIAL", evidence="The engine orchestrates multi-step missions (flight_recovery: refund + hotel + calendar + draft + case) with per-step approval, verification and visible intermediate states. There are NO compensating transactions: a failed step goes to reconcile or human review rather than automatic undo."),
 dict(n="20", t="Cron Jobs", problem="Some work must happen on a schedule, exactly once.",
  how="A scheduler enqueues jobs; a distributed lock or external orchestrator ensures only one instance claims each run. Store times in UTC.",
  diagram=[[("Scheduler 0 0 * * 0", "a"), ("Lock", "n"), ("Queue", "n")], [("3 servers -> 1 run", "ok")]],
  take="Cron enqueues; it does not do the heavy work. Watch time zones.",
  status="NOT IMPLEMENTED", evidence="No scheduler. Only recover_incomplete() runs at startup (app/main.py lifespan). Timestamps use UTC (utcnow). With a single instance there is no duplicate-run risk yet; adding schedulers needs a lock first."),
]

CHECKLIST = [
 ("Idempotency on payment/side-effect routes", "yes", "engine op_key + reconcile-not-resend"),
 ("Heavy logic in a queue, not synchronous", "no", "execution is synchronous"),
 ("Strict timeouts on external calls", "partial", "task timeout_ms; not audited everywhere"),
 ("Exponential backoff with jitter", "no", "not implemented"),
 ("Cache in front of the database", "no", "no cache layer"),
 ("Cron protected by a distributed lock", "n/a", "no cron yet"),
 ("Frontend survives a failing endpoint", "partial", "Bolna breaker returns 503 provider_circuit_open; other adapters have none"),
]

COL = {"n": ("var(--box)", "var(--line)"), "a": ("var(--accent-bg)", "var(--accent)"),
       "bad": ("var(--bad-bg)", "var(--bad)"), "ok": ("var(--ok-bg)", "var(--ok)")}
STATUS_CLASS = {"IMPLEMENTED": "s-ok", "PARTIAL": "s-part", "NOT IMPLEMENTED": "s-no"}


def svg(diagram) -> str:
    bw, bh, gx, gy, pad = 150, 44, 34, 40, 14
    cols = max(len(r) for r in diagram)
    w = pad * 2 + cols * bw + (cols - 1) * gx
    h = pad * 2 + len(diagram) * bh + (len(diagram) - 1) * gy
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" xmlns="http://www.w3.org/2000/svg">'
           '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
           '<path d="M0 0L10 5L0 10z" fill="var(--muted)"/></marker></defs>']
    pos = []
    for ri, row in enumerate(diagram):
        rw = len(row) * bw + (len(row) - 1) * gx
        x0 = (w - rw) / 2
        y = pad + ri * (bh + gy)
        pos.append([])
        for ci, (label, kind) in enumerate(row):
            x = x0 + ci * (bw + gx)
            fill, stroke = COL[kind]
            lines = _wrap(label)
            out.append(f'<rect x="{x:.0f}" y="{y}" width="{bw}" height="{bh}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
            for li, ln in enumerate(lines):
                ty = y + bh / 2 + (li - (len(lines) - 1) / 2) * 15 + 5
                out.append(f'<text x="{x + bw / 2:.0f}" y="{ty:.0f}" text-anchor="middle">{html.escape(ln)}</text>')
            pos[-1].append((x, y))
        for ci in range(len(row) - 1):
            x1, y1 = pos[-1][ci][0] + bw, pos[-1][ci][1] + bh / 2
            out.append(f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x1 + gx - 2:.0f}" y2="{y1:.0f}" stroke="var(--muted)" stroke-width="1.5" marker-end="url(#ah)"/>')
        if ri > 0:
            px, py = pos[ri - 1][len(pos[ri - 1]) // 2]
            cx, cy = pos[ri][len(row) // 2]
            out.append(f'<line x1="{px + bw / 2:.0f}" y1="{py + bh}" x2="{cx + bw / 2:.0f}" y2="{cy - 2}" stroke="var(--muted)" stroke-width="1.5" marker-end="url(#ah)"/>')
    out.append("</svg>")
    return "".join(out)


def _wrap(s: str, n: int = 19):
    words, lines, cur = s.split(), [], ""
    for wd in words:
        if len(cur) + len(wd) + 1 > n and cur:
            lines.append(cur)
            cur = wd
        else:
            cur = f"{cur} {wd}".strip()
    return (lines + [cur])[:2]


def build() -> str:
    cards = []
    for t in TOPICS:
        cards.append(f'''<article class="card" id="t{t["n"]}">
<header><span class="num">{t["n"]}</span><h2>{html.escape(t["t"])}</h2><span class="pill {STATUS_CLASS[t["status"]]}">{t["status"].title()}</span></header>
<p class="problem"><b>Problem.</b> {html.escape(t["problem"])}</p>
<div class="dia">{svg(t["diagram"])}</div>
<p><b>How it works.</b> {html.escape(t["how"])}</p>
<p class="take"><b>Takeaway.</b> {html.escape(t["take"])}</p>
<p class="ev"><b>In REDEEM.</b> {html.escape(t["evidence"])}</p>
</article>''')
    counts = {k: sum(1 for t in TOPICS if t["status"] == k) for k in STATUS_CLASS}
    cls = {"yes": "s-ok", "no": "s-no", "partial": "s-part", "n/a": "s-na"}
    rows = "".join(f'<tr><td>{html.escape(a)}</td><td><span class="pill {cls[b]}">{b}</span></td><td>{html.escape(c)}</td></tr>' for a, b, c in CHECKLIST)
    toc = "".join(f'<a href="#t{t["n"]}" class="{STATUS_CLASS[t["status"]]}">{t["n"]} {html.escape(t["t"])}</a>' for t in TOPICS)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>System Design Trail</title>
<style>
:root{{--bg:#16130f;--panel:#1f1b16;--box:#2a251f;--line:#4a4238;--text:#efe8de;--muted:#a89d8d;--accent:#ff7a1a;--accent-bg:#3a2412;--ok:#7bc47f;--ok-bg:#1f2e20;--bad:#e5645a;--bad-bg:#37201d}}
@media (prefers-color-scheme:light){{:root{{--bg:#f7f3ec;--panel:#fff;--box:#f1ebe0;--line:#cfc4b2;--text:#241f19;--muted:#6f6556;--accent:#d85d00;--accent-bg:#ffe9d6;--ok:#2e7d32;--ok-bg:#e3f2e3;--bad:#b3261e;--bad-bg:#fbe4e1}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:16px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:32px 16px 64px}}h1{{font-size:2rem;margin:0 0 4px}}h1 span{{color:var(--accent)}}
.sub{{color:var(--muted);margin:0 0 20px}}.summary{{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0 8px}}
.stat{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 16px}}.stat b{{font-size:1.5rem;display:block}}
.toc{{display:flex;flex-wrap:wrap;gap:6px;margin:16px 0 28px}}.toc a{{font-size:.8rem;text-decoration:none;color:var(--text);border:1px solid var(--line);border-left-width:4px;border-radius:6px;padding:3px 8px;background:var(--panel)}}
.toc a.s-ok{{border-left-color:var(--ok)}}.toc a.s-part{{border-left-color:var(--accent)}}.toc a.s-no{{border-left-color:var(--bad)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,480px),1fr));gap:16px}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px}}
.card header{{display:flex;align-items:center;gap:10px;flex-wrap:wrap}}.card h2{{font-size:1.15rem;margin:0;flex:1}}
.num{{font:700 .85rem ui-monospace,monospace;color:var(--accent);border:1px solid var(--accent);border-radius:6px;padding:1px 7px}}
.pill{{font-size:.72rem;font-weight:600;border-radius:99px;padding:2px 10px;border:1px solid}}.s-ok{{color:var(--ok);border-color:var(--ok)}}.s-part{{color:var(--accent);border-color:var(--accent)}}.s-no{{color:var(--bad);border-color:var(--bad)}}.s-na{{color:var(--muted);border-color:var(--muted)}}
.card p{{margin:.55rem 0;font-size:.93rem}}.dia{{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:8px;overflow-x:auto}}
.dia svg{{width:100%;height:auto;min-width:300px;display:block}}.dia text{{fill:var(--text);font:12px system-ui,sans-serif}}
.take{{border-left:3px solid var(--accent);padding-left:10px}}.ev{{color:var(--muted)}}.ev b{{color:var(--text)}}
table{{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden}}td,th{{padding:8px 12px;border-bottom:1px solid var(--line);text-align:left;font-size:.92rem}}
.tw{{overflow-x:auto}}h3{{margin:32px 0 10px}}footer{{margin-top:32px;color:var(--muted);font-size:.85rem}}
</style></head><body><main>
<h1>System Design <span>Trail</span></h1>
<p class="sub">20 foundational topics, each drawn and then checked against what REDEEM really does. Status words are evidence-based: see the "In REDEEM" line on each card. Generated by <code>scripts/build_system_design.py</code>.</p>
<div class="summary"><div class="stat"><b>{counts["IMPLEMENTED"]}</b>implemented</div><div class="stat"><b>{counts["PARTIAL"]}</b>partial</div><div class="stat"><b>{counts["NOT IMPLEMENTED"]}</b>not implemented</div></div>
<nav class="toc">{toc}</nav>
<section class="grid">{"".join(cards)}</section>
<h3>Production-readiness checklist (REDEEM, today)</h3>
<div class="tw"><table><thead><tr><th>Question</th><th>Answer</th><th>Evidence</th></tr></thead><tbody>{rows}</tbody></table></div>
<footer>Topics 1-20 are generic patterns; the status of each is specific to this repository at the commit that generated this page. Not-implemented items are listed in docs/OPEN_BLOCKERS.md terms: they are real gaps, not roadmap promises.</footer>
</main></body></html>'''


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    page = build()
    if "--check" in sys.argv:
        sys.exit(0 if OUT.exists() and OUT.read_text() == page else 1)
    OUT.write_text(page)
    print(f"wrote {OUT} ({len(page)} bytes)")
