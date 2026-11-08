# Cost per hire = Candidate annual CTC + Consulting fees + Recruiter fees, confirmed before Joined.
# Run against a NON-production database (see test_workflow.py for the command).
import os
import uuid
from datetime import date, timedelta

import pytest
import requests

API = os.environ.get("API_URL", "http://localhost:8001").rstrip("/") + "/api"
ADMIN = {"email": os.environ.get("ADMIN_EMAIL", "").lower(), "password": os.environ.get("ADMIN_PASSWORD", "")}
PW = "TestPass@123"
TAG = uuid.uuid4().hex[:6]
D = lambda n: (date.today() - timedelta(days=n)).isoformat()
S = {}


def sess(email=None, password=PW):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email or ADMIN["email"], "password": password if email else ADMIN["password"]})
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s


@pytest.fixture(scope="module")
def admin():
    return sess()


def ok(r):
    assert r.status_code == 200, f"{r.status_code}: {r.text}"
    return r.json()


def err(r, code=400, text=None):
    assert r.status_code == code, f"expected {code}, got {r.status_code}: {r.text}"
    if text:
        assert text.lower() in r.text.lower(), r.text


def to_offer_accepted(a, name, ctc=6):
    """New candidate taken to Offer Accepted through real records (screening, shortlisting, audited waiver, selection, offer)."""
    c = ok(a.post(f"{API}/candidates", json={"name": f"TEST_HC_{name}_{TAG}", "email": f"hc_{name.lower()}_{TAG}@mms.test", "requisition_id": S["req"], "force": True}))
    aid = next(x["id"] for x in ok(a.get(f"{API}/applications", params={"requisition_id": S["req"]})) if x["candidate_id"] == c["id"])
    ok(a.post(f"{API}/applications/{aid}/stage-reviews", json={"stage": "Screening", "date": D(20), "owner": "TEST_Screener", "decision": "Cleared"}))
    ok(a.post(f"{API}/applications/{aid}/stage-reviews", json={"stage": "Shortlisting", "date": D(19), "owner": "TEST_Screener", "decision": "Shortlisted"}))
    ok(a.post(f"{API}/applications/{aid}/interview-waiver", json={"reason": "Test: interviews covered elsewhere"}))
    ok(a.post(f"{API}/selections", json={"application_id": aid, "decision": "Selected", "selection_date": D(10), "decision_maker": "CTO",
                                         "compensation": ctc, "approval_status": "Approved"}))
    o = ok(a.post(f"{API}/offers", json={"application_id": aid, "designation": "Engineer", "ctc": ctc, "validity_date": D(-30)}))
    for act, d in (("submit", None), ("approve", None), ("release", D(8)), ("accept", D(6))):
        ok(a.post(f"{API}/offers/{o['id']}/action", json={"action": act, **({"date": d} if d else {})}))
    return c["id"], aid


def hc(a, aid, **kw):
    return a.put(f"{API}/applications/{aid}/hire-cost", json=kw)


def join(a, aid):
    return a.post(f"{API}/applications/{aid}/status", json={"status": "Joined", "joining_date": D(1)})


def app_of(a, aid):
    return ok(a.get(f"{API}/applications/{aid}"))


def test_00_setup(admin):
    admin.post(f"{API}/masters", json={"type": "recruiter", "name": "TEST_Screener"})  # screening owner / reviewer must be a recruiter
    for role, key in (("recruiter", "rec"), ("management", "mgmt"), ("interviewer", "iv")):
        S[f"email_{key}"] = f"hc_{key}_{TAG}@mms.test"
        ok(admin.post(f"{API}/users", json={"email": S[f"email_{key}"], "name": f"TEST_hc_{key}_{TAG}", "role": role, "password": PW}))
    rec = next(m["id"] for m in ok(admin.get(f"{API}/masters")) if m["type"] == "recruiter" and m["name"] == f"TEST_hc_rec_{TAG}")
    S["req"] = ok(admin.post(f"{API}/requisitions", json={"title": f"TEST_HC Role {TAG}", "positions": 10, "recruiter_id": rec,
                                                          "crf_date": D(60), "status": "Open"}))["id"]


# 1. all three positive — matches the brief's example (₹6,00,000 + ₹50,000 + ₹20,000 = ₹6,70,000)
def test_01_all_positive(admin):
    _, aid = to_offer_accepted(admin, "Positive")
    r = ok(hc(admin, aid, ctc=6, consulting_fee=0.5, recruiter_fee=0.2, total=999))  # client total is ignored
    assert r["hire_cost"]["total"] == 6.7
    ok(join(admin, aid))
    assert app_of(admin, aid)["status"] == "Joined"
    S["positive"] = aid


# 2-4. zero fees are allowed
@pytest.mark.parametrize("name,cf,rf,total", [("ZeroConsult", 0, 0.2, 6.2), ("ZeroRecruiter", 0.5, 0, 6.5), ("ZeroBoth", 0, 0, 6.0)])
def test_02_04_zero_fees(admin, name, cf, rf, total):
    _, aid = to_offer_accepted(admin, name)
    assert ok(hc(admin, aid, ctc=6, consulting_fee=cf, recruiter_fee=rf))["hire_cost"]["total"] == total
    ok(join(admin, aid))
    S[name] = aid


# 5-7. blanks are not zero
def test_05_07_blanks_rejected(admin):
    _, aid = to_offer_accepted(admin, "Blanks")
    S["blanks"] = aid
    err(hc(admin, aid, consulting_fee=0.5, recruiter_fee=0.2), 400, "annual ctc is required")
    err(hc(admin, aid, ctc=6, recruiter_fee=0.2), 400, "consulting fees is required")
    err(hc(admin, aid, ctc=6, consulting_fee=0.5), 400, "recruiter fees is required")
    err(hc(admin, aid, ctc=0, consulting_fee=0, recruiter_fee=0), 400, "greater than zero")
    assert app_of(admin, aid).get("hire_cost") is None


# 8. negatives, wrong currency, rupees typed into lakhs
def test_08_invalid_values(admin):
    aid = S["blanks"]
    err(hc(admin, aid, ctc=-6, consulting_fee=0, recruiter_fee=0), 400, "negative")
    err(hc(admin, aid, ctc=6, consulting_fee=-1, recruiter_fee=0), 400, "negative")
    err(hc(admin, aid, ctc=6, consulting_fee=0, recruiter_fee=-0.1), 400, "negative")
    err(hc(admin, aid, ctc=6, consulting_fee=0, recruiter_fee=0, currency="USD"), 400, "inr")
    err(hc(admin, aid, ctc=6, consulting_fee=0, recruiter_fee=0, ctc_basis="monthly"), 400, "annual")
    err(hc(admin, aid, ctc=600000, consulting_fee=0, recruiter_fee=0), 400, "lakhs")
    assert app_of(admin, aid).get("hire_cost") is None


# 9. Joined without confirmed cost — every route
def test_09_join_without_cost(admin):
    aid = S["blanks"]
    err(join(admin, aid), 400, "recruitment cost")
    rd = ok(admin.get(f"{API}/applications/{aid}/readiness", params={"target": "Joined"}))
    cost = next(s for s in rd["steps"] if s["key"] == "cost")
    assert cost["blocking"] and not cost["done"] and "cost" in rd["missing"]
    j = next(x for x in ok(admin.get(f"{API}/joinings", params={"requisition_id": S["req"]})) if x["application_id"] == aid)
    err(admin.put(f"{API}/joinings/{j['id']}", json={"status": "Joined", "actual_date": D(1)}), 400, "recruitment cost")
    got = ok(admin.get(f"{API}/joinings", params={"requisition_id": S["req"]}))
    assert next(x for x in got if x["id"] == j["id"])["status"] != "Joined" and app_of(admin, aid)["status"] == "Offer Accepted"


# 10. bypass attempts through the API
def test_10_api_bypass(admin):
    aid = S["blanks"]
    err(admin.post(f"{API}/applications/{aid}/status", json={"status": "Joined", "joining_date": D(1), "override_reason": "skip cost"}), 400)
    rec, mg, iv = sess(S["email_rec"]), sess(S["email_mgmt"]), sess(S["email_iv"])
    err(join(rec, aid), 400, "recruitment cost")
    for s in (mg, iv):
        assert hc(s, aid, ctc=6, consulting_fee=0, recruiter_fee=0).status_code in (403, 404)
    _, early = to_offer_accepted(admin, "Early")
    # cost cannot be confirmed before the offer is accepted
    c = ok(admin.post(f"{API}/candidates", json={"name": f"TEST_HC_New_{TAG}", "email": f"hc_new_{TAG}@mms.test", "requisition_id": S["req"], "force": True}))
    new = next(x["id"] for x in ok(admin.get(f"{API}/applications", params={"requisition_id": S["req"]})) if x["candidate_id"] == c["id"])
    err(hc(admin, new, ctc=6, consulting_fee=0, recruiter_fee=0), 400, "offer is accepted")
    assert app_of(admin, aid)["status"] == "Offer Accepted"


# 11. authorised change (HR / Recruiter persona and Super Admin) needs a reason
def test_11_authorised_change(admin):
    aid = S["positive"]
    err(hc(admin, aid, ctc=6, consulting_fee=0.6, recruiter_fee=0.2), 400, "reason")
    r = ok(hc(admin, aid, ctc=6, consulting_fee=0.6, recruiter_fee=0.2, reason="Final partner invoice received"))
    assert r["hire_cost"]["total"] == 6.8 and r["hire_cost"]["version"] == 2
    rec = sess(S["email_rec"])
    r = ok(hc(rec, aid, ctc=6.5, consulting_fee=0.6, recruiter_fee=0.2, reason="CTC revised at joining"))
    assert r["hire_cost"]["total"] == 7.3 and r["hire_cost"]["updated_by"] == f"TEST_hc_rec_{TAG}"
    assert r["hire_cost"]["confirmed_by"] != r["hire_cost"]["updated_by"]  # original confirmer kept


# 12. unauthorised change
def test_12_unauthorised_change(admin):
    aid = S["positive"]
    for key in ("mgmt", "iv"):
        assert hc(sess(S[f"email_{key}"]), aid, ctc=1, consulting_fee=0, recruiter_fee=0, reason="x").status_code in (403, 404)
    assert app_of(admin, aid)["hire_cost"]["total"] == 7.3


# 13. audit history
def test_13_audit_history(admin):
    aid = S["positive"]
    h = ok(admin.get(f"{API}/applications/{aid}/hire-cost"))["history"]
    assert [x["action"] for x in h] == ["Confirmed", "Updated", "Updated"]
    assert h[1]["previous"]["total"] == 6.7 and h[1]["new"]["total"] == 6.8 and h[1]["reason"]
    assert h[2]["previous"]["ctc"] == 6 and h[2]["new"]["ctc"] == 6.5 and h[2]["by"] == f"TEST_hc_rec_{TAG}"
    assert all(x["at"] and x["by_id"] for x in h)
    acts = ok(admin.get(f"{API}/activity"))
    acts = acts if isinstance(acts, list) else acts.get("items", [])
    mine = [x for x in acts if x.get("entity_id") == aid and x["action"].startswith("hire_cost")]
    assert len(mine) == 3 and "→" in mine[0]["details"]


# 14. dashboard / analytics / report
def test_14_analytics(admin):
    a = ok(admin.get(f"{API}/analytics", params={"requisition_id": S["req"]}))
    c = a["cost"]
    # joined: Positive 7.3, ZeroConsult 6.2, ZeroRecruiter 6.5, ZeroBoth 6.0
    assert c["hires"] == 4 and c["joined"] == 4 and c["unconfirmed"] == 0
    assert c["total"] == 26.0 and c["cost_per_hire"] == 6.5
    assert c["ctc_total"] == 24.5 and c["consulting_total"] == 1.1 and c["recruiter_total"] == 0.4
    rows = {r["code"]: r for r in c["hire_costs"]}
    pos = next(r for r in rows.values() if r["application_id"] == S["positive"])
    assert pos["total"] == 7.3 == round(pos["ctc"] + pos["consulting_fee"] + pos["recruiter_fee"], 4)
    r = admin.get(f"{API}/reports/cost-per-hire", params={"format": "csv", "requisition_id": S["req"]})
    assert r.status_code == 200 and "Cost per Hire (L)" in r.text and "7.3" in r.text
    summary = admin.get(f"{API}/reports/summary", params={"format": "csv", "period": "monthly"})
    assert summary.status_code == 200 and "Hires with Confirmed Cost" in summary.text
    # a requisition cannot close while a joined hire lacks confirmed cost — here all are confirmed, so cost is not listed
    rr = admin.put(f"{API}/requisitions/{S['req']}", json={"status": "Closed", "closure_reason": "test"})
    assert "confirmed recruitment cost" not in rr.text
