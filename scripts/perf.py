"""Measured in-process performance (SQLite, TestClient, single machine). Not a production load test."""
import json, os, resource, statistics, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
os.environ["REDEEM_DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp(prefix='redeem-perf-')}/p.db"
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.core.security import limiter  # noqa: E402
from app.main import app  # noqa: E402

limiter.check = lambda *a, **k: None  # rate limiting disabled for this measurement only
from app.models import ActionEvent  # noqa: E402

init_db()
c = TestClient(app)
me = c.post("/api/v1/auth/register", json={"email": "perf@example.com", "password": "correct-horse-battery", "name": "Perf"}).json()
H = {"X-CSRF-Token": me["csrf_token"]}
rss = lambda: resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # noqa: E731
pct = lambda xs, p: sorted(xs)[min(len(xs) - 1, int(len(xs) * p))]  # noqa: E731


def timed(fn, n):
    out = []
    for _ in range(n):
        t = time.perf_counter(); fn(); out.append((time.perf_counter() - t) * 1000)
    return {"n": n, "p50_ms": round(statistics.median(out), 2), "p95_ms": round(pct(out, 0.95), 2)}


r = {"environment": "rate limiter disabled for the run; single process, SQLite, TestClient (no network); fixture providers"}
rss0 = rss()
ids = []
def create():
    ids.append(c.post("/api/v1/missions", json={"intent": "Flight FA2041 cancelled refund and calendar"}, headers=H).json()["id"])
r["mission_create_plan"] = timed(create, 60)
r["mission_get"] = timed(lambda: c.get(f"/api/v1/missions/{ids[0]}"), 100)

cnt = iter(range(10_000))
def full():
    m = c.post("/api/v1/missions", json={"intent": f"Case {next(cnt)}: my telecom bill is wrong, broadband outage"}, headers=H).json()
    ap = [{"action_id": a["id"], "digest": a["digest"]} for a in m["plan"]["actions"]]
    c.post(f"/api/v1/missions/{m['id']}/approve", json={"approvals": ap}, headers=H)
    assert c.post(f"/api/v1/missions/{m['id']}/execute", headers=H).json()["status"] == "VERIFIED"
r["full_mission_approve_execute_verify"] = timed(full, 20)

with SessionLocal() as s:
    n_ev = s.scalar(select(func.count()).select_from(ActionEvent))
r["ledger_events_total"] = n_ev

t = time.perf_counter()
with ThreadPoolExecutor(8) as ex:
    res = list(ex.map(lambda _: c.get(f"/api/v1/missions/{ids[1]}").status_code, range(200)))
el = time.perf_counter() - t
r["concurrent_reads_8_threads"] = {"requests": 200, "ok": res.count(200), "requests_per_second": round(200 / el, 1)}
r["peak_rss_mb_after_imports"], r["peak_rss_mb_end"] = round(rss0, 1), round(rss(), 1)
out = ROOT / "docs" / "PERF_RESULTS.json"
out.write_text(json.dumps(r, indent=1)); print(json.dumps(r, indent=1))
