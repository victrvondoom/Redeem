from conftest import approve_all

B = "/api/v1"


def test_overview_counts_and_attention_come_from_real_state(api):
    o = api.get(f"{B}/overview").json()
    assert o["counts"]["missions_total"] == 0 and o["attention"] == [] and "nothing here is a benchmark" in o["scope"]
    m = api.post(f"{B}/missions", {"intent": "Flight FA2041 cancelled refund"}).json()                    # waits for approval
    api.post(f"{B}/cases", {"text": "My flight was cancelled and I want a refund from the airline."})        # waits for facts
    c = api.post(f"{B}/cases", {"text": "My Jio postpaid bill shows Rs 1,299 of extra charges. Complaint no: CMP-8812 no resolution."}).json()
    o = api.get(f"{B}/overview").json()
    kinds = {a["kind"] for a in o["attention"]}
    assert {"approval", "case_info", "case_approval"} <= kinds
    assert o["counts"]["missions_active"] == 1 and o["counts"]["cases_total"] == 3      # 2 explicit + the travel case the mission opened
    assert any(a["href"] == f"/app/missions/{m['id']}" for a in o["attention"]) and any(a["href"] == f"/app/cases/{c['id']}" for a in o["attention"])
    approve_all(api, m)
    api.post(f"{B}/missions/{m['id']}/execute")
    o = api.get(f"{B}/overview").json()
    assert o["counts"]["verified_outcomes"] == 1 and not any(a["kind"] == "approval" for a in o["attention"])
    assert any(r["type"] == "VERIFIED" for r in o["recent"])


def test_overview_is_tenant_scoped(api, api2):
    api.post(f"{B}/missions", {"intent": "Flight FA2041 cancelled refund"})
    o = api2.get(f"{B}/overview").json()
    assert o["counts"]["missions_total"] == 0 and o["attention"] == [] and o["recent"] == []


def test_quality_lab_runs_a_real_benchmark_in_a_separate_process_and_stores_raw_results(api, api2, db):
    from app.models import Mission
    before = db.query(Mission).count()
    r = api.post(f"{B}/quality/runs", {"seed": 3, "n": 1}).json()
    assert r["status"] == "DONE" and r["duration_seconds"] > 0 and "separate process" in r["mode"]
    s = r["summary"]["C_redeem"]["TOTAL"]
    assert s["n"] == 7 and s["wrong_target"] == 0 and s["duplicate"] == 0 and s["false_success"] == 0   # denominators: 7 scenarios x 1 seed
    assert r["summary"]["A_naive"]["TOTAL"]["false_success"] > 0
    db.expire_all()
    assert db.query(Mission).count() == before                                                          # the benchmark never touched this database
    raw = api.get(f"{B}/quality/runs/{r['id']}/raw")
    assert raw.status_code == 200 and '"raw_trials"' in raw.text
    assert [x["id"] for x in api.get(f"{B}/quality/runs").json()["items"]] == [r["id"]]
    assert api2.get(f"{B}/quality/runs").json()["items"] == [] and api2.get(f"{B}/quality/runs/{r['id']}/raw").status_code == 404
    assert api.post(f"{B}/quality/runs", {"seed": 3, "n": 99}).status_code == 422
