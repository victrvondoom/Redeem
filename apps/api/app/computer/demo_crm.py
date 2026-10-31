"""A small CRM web app with synthetic records, served by REDEEM so the computer agent has a real application to
operate through its UI (mouse and keyboard). Every page is labelled synthetic. "Send message" records a simulated
send and delivers nothing; the agent never clicks it without an approval bound to that exact action."""
from __future__ import annotations

import html
import secrets

from fastapi import APIRouter, Body, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from ..core.deps import err
from ..db import get_db, utcnow
from ..models import DemoCrmContact

router = APIRouter(prefix="/demo/crm", tags=["demo-crm"])
SEED = [("Priya Sharma", "priya.sharma@example.test", "+91 90000 00001", "Sharma Textiles"), ("Arjun Mehta", "arjun.mehta@example.test", "+91 90000 00002", "Mehta Logistics"),
        ("Kavya Iyer", "kavya.iyer@example.test", "+91 90000 00003", "Iyer Clinics"), ("Rohan Das", "rohan.das@example.test", "+91 90000 00004", "Das Electricals")]
METHODS = ["Email", "Phone", "WhatsApp", "SMS"]


def ensure(db, tenant_id: str) -> str:
    row = db.scalar(select(DemoCrmContact).where(DemoCrmContact.tenant_id == tenant_id))
    if row:
        return row.workspace_key
    key = secrets.token_urlsafe(18)
    for n, e, p, c in SEED:
        db.add(DemoCrmContact(tenant_id=tenant_id, workspace_key=key, name=n, email=e, phone=p, company=c, followups=[], drafts=[], sent=[]))
    db.commit()
    return key


def _rows(db, key: str):
    rows = list(db.scalars(select(DemoCrmContact).where(DemoCrmContact.workspace_key == key).order_by(DemoCrmContact.name)))
    if not rows:
        raise err(404, "not_found", "Unknown demo CRM")
    return rows


def _one(db, key, cid) -> DemoCrmContact:
    c = db.scalar(select(DemoCrmContact).where(DemoCrmContact.workspace_key == key, DemoCrmContact.id == cid))
    if not c:
        raise err(404, "not_found", "No such contact")
    return c


def as_json(c: DemoCrmContact) -> dict:
    return {"id": c.id, "name": c.name, "email": c.email, "phone": c.phone, "company": c.company, "preferred_contact": c.preferred_contact,
            "followups": c.followups, "drafts": c.drafts, "sent": c.sent}


CSS = """body{font:18px/1.45 Arial,Helvetica,sans-serif;margin:0;background:#fff;color:#111}header{background:#1d1b19;color:#fff;padding:10px 24px;font-size:18px}
main{padding:14px 24px}input,textarea{font:18px Arial;padding:6px 8px;border:1px solid #888;border-radius:4px}button{font:18px Arial;padding:6px 14px;border:1px solid #444;border-radius:4px;background:#f3f3f3;cursor:pointer}
a{color:#0b57d0;text-decoration:none}.row{display:flex;gap:28px}.col{flex:1}h1{font-size:24px;margin:4px 0 8px}h2{font-size:19px;margin:12px 0 6px}label{margin-right:18px}
.muted{color:#555}.ok{color:#116611}"""


def page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"<!doctype html><html><head><meta charset=utf-8><title>{html.escape(title)} - Demo CRM</title><style>{CSS}</style></head><body>"
                        f"<header>REDEEM Demo CRM (synthetic data)</header><main>{body}</main></body></html>",
                        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})


@router.get("/{key}/", response_class=HTMLResponse)
def list_page(key: str, db=Depends(get_db)):
    _rows(db, key)
    return page("Customers", """<h1>Customers</h1><input id=q placeholder="Search customers" aria-label="Search customers" style="width:420px">
<ul id=list style="font-size:20px;line-height:2"></ul><script>
async function load(){const r=await fetch('api/contacts?q='+encodeURIComponent(q.value));const c=await r.json();
list.innerHTML=c.map(x=>`<li><a href="c/${x.id}">${x.name}</a> <span class=muted>${x.company}</span></li>`).join('')||'<li>No customers match</li>';}
q.oninput=load;load();</script>""")


@router.get("/{key}/c/{cid}", response_class=HTMLResponse)
def record_page(key: str, cid: str, db=Depends(get_db)):
    c = _one(db, key, cid)
    radios = "".join(f'<label><input type=radio name=pref value="{m}"> {m}</label>' for m in METHODS)
    return page(c.name, f"""<a href="../">All customers</a><h1>Contact record: {html.escape(c.name)}</h1>
<div class=row><div class=col><div class=muted>{html.escape(c.company)} | {html.escape(c.email)} | {html.escape(c.phone)}</div>
<h2>Preferred contact method</h2><div id=current></div><div style="margin:8px 0">{radios}</div><button id=savec>Save contact</button> <span id=st class=ok></span>
<h2>Follow-ups</h2><ul id=fu></ul><input id=fd placeholder="Follow-up date" style="width:170px"> <input id=ft placeholder="Time" style="width:90px">
<button id=addf>Add follow-up</button> <span id=fst class=ok></span></div>
<div class=col><h2>Message draft</h2><textarea id=dr rows=3 style="width:95%" placeholder="Write the message draft"></textarea><br>
<button id=saved>Save draft</button> <button id=send>Send message</button> <span id=dst class=ok></span>
<h2>Saved drafts</h2><ul id=drs></ul><h2>Messages sent</h2><ul id=sent></ul></div></div>
<script>
const API='../api/contacts/{c.id}';let C;
function render(){{current.textContent='Current preferred contact: '+C.preferred_contact;
document.querySelectorAll('input[name=pref]').forEach(r=>r.checked=(r.value===C.preferred_contact));
fu.innerHTML=C.followups.map(f=>`<li>Follow-up ${{f.date}} ${{f.time}}</li>`).join('')||'<li class=muted>No follow-ups</li>';
drs.innerHTML=C.drafts.map(d=>`<li>Draft: ${{d.body.slice(0,60)}}</li>`).join('')||'<li class=muted>No drafts</li>';
sent.innerHTML=C.sent.map(d=>`<li>Sent: ${{d.body.slice(0,60)}}</li>`).join('')||'<li class=muted>No messages sent</li>';}}
async function load(){{C=await (await fetch(API)).json();render();}}
async function post(p,b){{const r=await fetch(API+p,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(b)}});const j=await r.json();if(r.ok){{C=j;render();}}return [r.ok,j];}}
savec.onclick=async()=>{{const v=(document.querySelector('input[name=pref]:checked')||{{}}).value;const [ok]=await post('/preferred',{{value:v}});st.textContent=ok?'Contact saved':'Save failed';}};
addf.onclick=async()=>{{const [ok,j]=await post('/followups',{{date:fd.value,time:ft.value}});fst.textContent=ok?'Follow-up added':('Error: '+j.error.message);if(ok){{fd.value='';ft.value='';}}}};
saved.onclick=async()=>{{const [ok]=await post('/drafts',{{body:dr.value}});dst.textContent=ok?'Draft saved':'Draft failed';if(ok)dr.value='';}};
send.onclick=async()=>{{const [ok]=await post('/send',{{body:dr.value}});dst.textContent=ok?'Message sent (simulated)':'Send failed';}};
load();</script>""")


@router.get("/{key}/api/contacts")
def api_list(key: str, q: str = "", db=Depends(get_db)):
    return [as_json(c) for c in _rows(db, key) if q.lower().strip() in c.name.lower()]


@router.get("/{key}/api/contacts/{cid}")
def api_get(key: str, cid: str, db=Depends(get_db)):
    return as_json(_one(db, key, cid))


@router.post("/{key}/api/contacts/{cid}/preferred")
def api_pref(key: str, cid: str, body: dict = Body(...), db=Depends(get_db)):
    c = _one(db, key, cid)
    if body.get("value") not in METHODS:
        raise err(422, "invalid", "Choose a contact method")
    c.preferred_contact = body["value"]
    db.commit()
    return as_json(c)


@router.post("/{key}/api/contacts/{cid}/followups")
def api_followup(key: str, cid: str, body: dict = Body(...), db=Depends(get_db)):
    import re
    c = _one(db, key, cid)
    d, t = str(body.get("date", "")).strip(), str(body.get("time", "")).strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) or not re.fullmatch(r"\d{1,2}:\d{2}", t):
        raise err(422, "invalid", "Date must be YYYY-MM-DD and time HH:MM")
    c.followups = [*c.followups, {"date": d, "time": t, "at": utcnow().isoformat()}]
    db.commit()
    return as_json(c)


@router.post("/{key}/api/contacts/{cid}/drafts")
def api_draft(key: str, cid: str, body: dict = Body(...), db=Depends(get_db)):
    c = _one(db, key, cid)
    b = str(body.get("body", "")).strip()[:1000]
    if not b:
        raise err(422, "invalid", "Draft is empty")
    c.drafts = [*c.drafts, {"body": b, "at": utcnow().isoformat()}]
    db.commit()
    return as_json(c)


@router.post("/{key}/api/contacts/{cid}/send")
def api_send(key: str, cid: str, body: dict = Body(...), db=Depends(get_db)):
    c = _one(db, key, cid)
    c.sent = [*c.sent, {"body": str(body.get("body", ""))[:1000], "at": utcnow().isoformat(), "simulated": True}]
    db.commit()
    return as_json(c)
