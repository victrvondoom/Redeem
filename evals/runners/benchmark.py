"""Seeded policy benchmark on the stateful booking fixture.

Policies (what each executor is *designed* to do; these are our own reference executors, not other products):
  A naive      : executes the first instruction, retries timeouts blindly, trusts the provider's OK.
  B checked    : like A, but sends an idempotency key and checks the target exists.
  C redeem     : the real REDEEM engine (revisions, digest approvals, reconcile, independent verifier).

Ground truth is read from fixture tables after each trial, never from the policy's own report.
Run:  python evals/runners/benchmark.py --n 30 --seed 7
"""
import argparse, json, os, random, sys, tempfile, time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))
os.environ["REDEEM_DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp(prefix='redeem-bench-')}/b.db"

from sqlalchemy import select  # noqa: E402

from app.connectors.base import ProviderTimeout  # noqa: E402
from app.connectors.booking import BookingConnector  # noqa: E402
from app.db import Base, SessionLocal, engine as db_engine  # noqa: E402
from app.fixtures.seed import seed_tenant  # noqa: E402
from app.models import (Action, ActionApproval, FxBooking, FxFault, FxRequest, Membership, Mission,  # noqa: E402
                        ProviderOperation, Tenant, User, Workspace)
from app.orchestration import engine as eng  # noqa: E402

SCENARIOS = ["user_correction", "lost_ack", "silent_drop", "stale_target", "restart_mid_dispatch"]
POLICIES = ["A_naive", "B_checked", "C_redeem"]


def new_tenant(db):
    t = Tenant(name="bench")
    u = User(email=f"b{time.perf_counter_ns()}@bench.invalid", name="Bench", password_hash="x")
    db.add_all([t, u]); db.flush()
    w = Workspace(tenant_id=t.id, name="w"); db.add(w); db.flush()
    db.add(Membership(user_id=u.id, tenant_id=t.id, workspace_id=w.id)); seed_tenant(db, t.id); db.commit()
    bk = {b.ref: b for b in db.scalars(select(FxBooking).where(FxBooking.tenant_id == t.id))}
    return t, u, w, bk


def counts(db, tenant, correct, wrong):
    def n(b):
        return len(list(db.scalars(select(FxRequest).where(FxRequest.tenant_id == tenant, FxRequest.booking_id == b.id,
                                                           FxRequest.kind == "refund_request"))))
    db.expire_all()
    return n(correct), n(wrong)


def approve_all(db, m, uid):
    items = [{"action_id": a.id, "digest": a.digest} for a in eng._actions(db, m) if a.status == "AWAITING_APPROVAL"]
    eng.approve(db, m, uid, items); db.commit()


def c_start(db, t, u, w, first):
    m = Mission(tenant_id=t.id, workspace_id=w.id, user_id=u.id, intent="Flight cancelled, refund please")
    db.add(m); db.flush(); eng.start_mission(db, m); db.commit()
    eng.bind(db, m, "booking_id", first.id); db.commit()
    return m


def run_trial(policy, scenario, rng, trial):
    with SessionLocal() as db:
        t, u, w, bk = new_tenant(db)
        a_, b_ = (bk["FA2041"], bk["FA2087"]) if rng.random() < 0.5 else (bk["FA2087"], bk["FA2041"])
        first, correct = (a_, b_) if scenario == "user_correction" else (b_, b_)
        wrong = a_ if scenario == "user_correction" else a_
        conn = BookingConnector(db, t.id)
        params = lambda b: {"booking_id": b.id, "amount_paise": b.amount_paise}  # noqa: E731
        key = None if policy == "A_naive" else f"b-{trial}-{scenario}"
        reported_success, expects_no_effect = False, scenario == "stale_target"
        start = time.perf_counter()

        def submit_retrying(b):
            try:
                conn.submit("refund_request", params(b), key)
            except ProviderTimeout:
                conn.submit("refund_request", params(b), key)  # blind retry (A: no key => duplicate)

        if scenario in ("lost_ack", "silent_drop"):
            db.add(FxFault(tenant_id=t.id, kind="ack_loss" if scenario == "lost_ack" else "silent_drop", remaining=1)); db.commit()
        if scenario == "stale_target":
            pass

        if policy in ("A_naive", "B_checked"):
            if scenario == "stale_target":
                correct.version += 1; db.commit()  # provider-side change after the plan/approval
            if scenario == "restart_mid_dispatch":
                conn.submit("refund_request", params(first), key)  # applied, then the process "died"
                submit_retrying(first)                              # restart: no memory, resend
            else:
                submit_retrying(first)  # user_correction: correction never reaches an already-queued instruction
            reported_success = True
        else:
            m = c_start(db, t, u, w, first)
            if scenario == "user_correction":
                approve_all(db, m, u.id)
                eng.bind(db, m, "booking_id", correct.id); db.commit()
                approve_all(db, m, u.id)
                eng.execute(db, m)
            elif scenario == "stale_target":
                correct.version += 1; db.commit()
                try:
                    approve_all(db, m, u.id)
                except eng.EngineError:
                    db.rollback(); db.commit()
            elif scenario == "restart_mid_dispatch":
                approve_all(db, m, u.id)
                act = db.scalar(select(Action).where(Action.mission_id == m.id, Action.kind == "refund_request"))
                eng.transition(db, m, "EXECUTING"); act.status = "DISPATCHING"
                db.add(ProviderOperation(tenant_id=t.id, action_id=act.id, provider="booking_fixture",
                                         idempotency_key=act.idempotency_key, status="DISPATCHING"))
                eng.emit(db, m, "DISPATCHING", {"snapshot": {}}, act.id); db.commit()
                conn.submit("refund_request", act.params, act.idempotency_key)
                eng.recover_incomplete(db)
            else:
                approve_all(db, m, u.id); eng.execute(db, m)
            db.refresh(m)
            reported_success = m.status == "VERIFIED"  # PARTIALLY_VERIFIED is an honest non-success
        elapsed = time.perf_counter() - start
        n_ok, n_wrong = counts(db, t.id, correct, wrong)
        if expects_no_effect:
            completed = (n_ok + n_wrong == 0) and not reported_success
        elif scenario == "silent_drop":  # the effect cannot exist; the only correct behaviour is not claiming success
            completed = n_wrong == 0 and not reported_success
        else:
            completed = n_ok == 1 and n_wrong == 0
        return {"policy": policy, "scenario": scenario, "trial": trial, "requests_on_correct": n_ok,
                "requests_on_wrong": n_wrong, "reported_success": reported_success,
                "correct_outcome": completed, "wrong_target": n_wrong > 0, "duplicate": n_ok > 1,
                "false_success": reported_success and not completed,
                "unauthorized_execution": expects_no_effect and (n_ok + n_wrong) > 0, "seconds": round(elapsed, 4)}


def summarise(trials):
    out = {}
    for p in POLICIES:
        for s in SCENARIOS:
            rows = [t for t in trials if t["policy"] == p and t["scenario"] == s]
            n = len(rows)
            out.setdefault(p, {})[s] = {"n": n, **{k: sum(r[k] for r in rows) for k in
                                                   ("correct_outcome", "wrong_target", "duplicate", "false_success", "unauthorized_execution")},
                                        "mean_seconds": round(sum(r["seconds"] for r in rows) / n, 4)}
        rows = [t for t in trials if t["policy"] == p]
        out[p]["TOTAL"] = {"n": len(rows), **{k: sum(r[k] for r in rows) for k in
                                              ("correct_outcome", "wrong_target", "duplicate", "false_success", "unauthorized_execution")}}
    return out


def main(n=30, seed=7, write=True):
    Base.metadata.drop_all(db_engine); Base.metadata.create_all(db_engine)
    rng = random.Random(seed)
    trials = [run_trial(p, s, rng, i) for s in SCENARIOS for p in POLICIES for i in range(n)]
    result = {"generated_at": datetime.now(UTC).isoformat(), "seed": seed, "trials_per_cell": n, "scope": "local stateful fixture; no live provider",
              "caveat": "Policies A/B are our own reference executors modelling stated capabilities; results do not generalise to other products or to live providers.",
              "summary": summarise(trials), "raw_trials": trials}
    if write:
        path = ROOT / "evals" / "reports" / "benchmark_results.json"
        path.write_text(json.dumps(result, indent=1)); print(f"wrote {path}")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=30); ap.add_argument("--seed", type=int, default=7)
    r = main(**vars(ap.parse_args()))
    for p, rows in r["summary"].items():
        t = rows["TOTAL"]
        print(f"{p:10s} n={t['n']} correct={t['correct_outcome']} wrong_target={t['wrong_target']} dup={t['duplicate']} false_success={t['false_success']} unauthorized={t['unauthorized_execution']}")
