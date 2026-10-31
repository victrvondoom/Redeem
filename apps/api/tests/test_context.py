from sqlalchemy import select, text

from app.models import ConversationTurn

B = "/api/v1"
FLIGHT = "My flight FA2041 was cancelled, I need a refund"


def mission(api, intent=FLIGHT):
    r = api.post(f"{B}/missions", {"intent": intent, "language": "en", "source": "text"})
    assert r.status_code == 201, r.text
    return r.json()


def test_context_turns_are_persisted_encrypted_and_ordered(api, db):
    m = mission(api)
    api.post(f"{B}/missions/{m['id']}/utterance", {"text": "pause"})
    turns = api.get(f"{B}/context?ref_id={m['id']}").json()["turns"]
    assert [(t["channel"], t["role"]) for t in turns][:2] == [("mission", "user"), ("mission", "assistant")]
    assert turns[0]["text"] == FLIGHT and any(t["channel"] == "command" for t in api.get(f"{B}/context").json()["turns"])
    raw = db.execute(text("select text_enc from conversation_turns")).scalars().all()
    assert raw and all(r.startswith("enc2t:") and "FA2041" not in r for r in raw)


def test_short_followup_inherits_the_previous_missions_entities_but_a_new_reference_does_not(api):
    first = mission(api)
    if not first.get("bindings"):  # bind the booking through the normal clarification path if the engine asked
        cl = first.get("clarification")
        if cl:
            api.post(f"{B}/missions/{first['id']}/bind", {"role": cl["role"], "value": cl["candidates"][0]["id"]})
    follow = mission(api, "also move my hotel")
    evs = [e["type"] for e in api.get(f"{B}/missions/{follow['id']}/events").json()["items"]]
    prev_bound = bool(api.get(f"{B}/missions/{first['id']}").json().get("bindings"))
    assert ("CONTEXT_USED" in evs) == prev_bound
    other = mission(api, "also check FA2087 refund")
    assert "CONTEXT_USED" not in [e["type"] for e in api.get(f"{B}/missions/{other['id']}/events").json()["items"]]


def test_timeline_merges_every_history_source_with_filters_search_and_isolation(api, api2):
    m = mission(api)
    api.post(f"{B}/documents", files={"file": ("receipt.txt", b"refund of 500", "text/plain")})
    api.post(f"{B}/memory/ingest", {"utterance": "window", "expected_field": "travel.seat_preference"})
    t = api.get(f"{B}/timeline").json()
    assert {"mission", "document", "memory", "conversation", "activity"} <= set(t["counts"]) and t["total"] == sum(t["counts"].values())
    assert [i["at"] for i in t["items"]] == sorted((i["at"] for i in t["items"]), reverse=True)
    assert all(i["kind"] == "mission" for i in api.get(f"{B}/timeline?kind=mission").json()["items"])
    assert api.get(f"{B}/timeline?q=receipt").json()["items"][0]["title"] == "receipt.txt"
    assert api.get(f"{B}/timeline?limit=2").json()["items"].__len__() == 2
    assert api2.get(f"{B}/timeline").json()["total"] == 0 and m["id"] not in str(api2.get(f"{B}/timeline").json())
    assert api.get(f"{B}/timeline?kind=bogus").status_code == 422


def test_graph_links_user_memory_missions_entities_documents_and_is_private(api, api2):
    api.post(f"{B}/memory/ingest", {"utterance": "window", "expected_field": "travel.seat_preference"})
    m = mission(api)
    g = api.get(f"{B}/graph").json()
    kinds = {n["kind"] for n in g["nodes"]}
    assert {"user", "memory", "mission"} <= kinds
    assert any(e["rel"] == "prefers" for e in g["edges"]) and any(e["rel"] == "requested" and e["target"] == f"mis:{m['id']}" for e in g["edges"])
    ids = {n["id"] for n in g["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in g["edges"])            # no dangling edges
    assert any("window" in n["label"] for n in g["nodes"])
    g2 = api2.get(f"{B}/graph").json()
    assert {n["kind"] for n in g2["nodes"]} == {"user"} and g2["edges"] == []


def test_forget_context_and_account_deletion_remove_turns(api, db):
    m = mission(api)
    assert api.delete(f"{B}/context?ref_id={m['id']}").json()["deleted"] >= 2
    assert api.get(f"{B}/context?ref_id={m['id']}").json()["turns"] == []
    mission(api)
    assert api.get(f"{B}/privacy/export").json()["conversation_context"]
    api.delete(f"{B}/users/me")
    db.expire_all()
    assert db.scalar(select(ConversationTurn)) is None
