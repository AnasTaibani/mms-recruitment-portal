# Management members can also interview (additive Interviewer capability) — nothing else is added.
# Run against a NON-production database (see test_workflow.py).
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
RATINGS = {k: 4 for k in ["technical", "communication", "problem_solving", "relevant_experience", "role_fit", "overall"]}
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


def denied(r):
    assert r.status_code in (403, 404), f"expected 403/404, got {r.status_code}: {r.text}"


def test_00_setup(admin):
    admin.post(f"{API}/masters", json={"type": "recruiter", "name": "TEST_Screener"})  # screening owner / reviewer must be a recruiter
    for role, key, desig in (("management", "mg", "VP Engineering"), ("management", "mg2", "CFO"), ("interviewer", "iv", "Tech Lead"), ("recruiter", "rec", "HR")):
        S[f"email_{key}"] = f"mi_{key}_{TAG}@mms.test"
        S[f"user_{key}"] = ok(admin.post(f"{API}/users", json={"email": S[f"email_{key}"], "name": f"TEST_mi_{key}_{TAG}", "role": role,
                                                               "password": PW, "designation": desig}))
    ms = ok(admin.get(f"{API}/masters"))
    S["masters"] = ms
    pick = lambda key, t: next((m for m in ms if m["type"] == t and m.get("user_id") == S[f"user_{key}"]["id"]), None)
    S["m_mg"], S["m_mg2"], S["m_iv"] = pick("mg", "interviewer"), pick("mg2", "interviewer"), pick("iv", "interviewer")
    S["m_rec"] = pick("rec", "recruiter")
    req = ok(admin.post(f"{API}/requisitions", json={"title": f"TEST_MI Role {TAG}", "positions": 2, "recruiter_id": S["m_rec"]["id"], "crf_date": D(30), "status": "Open"}))
    S["req"] = req["id"]
    for n in ("one", "two"):
        c = ok(admin.post(f"{API}/candidates", json={"name": f"TEST_MI {n} {TAG}", "email": f"mi_{n}_{TAG}@mms.test", "requisition_id": S["req"], "force": True}))
        aid = next(x["id"] for x in ok(admin.get(f"{API}/applications", params={"requisition_id": S["req"]})) if x["candidate_id"] == c["id"])
        ok(admin.post(f"{API}/applications/{aid}/stage-reviews", json={"stage": "Screening", "date": D(5), "owner": "TEST_Screener", "decision": "Cleared"}))
        ok(admin.post(f"{API}/applications/{aid}/stage-reviews", json={"stage": "Shortlisting", "date": D(5), "owner": "TEST_Screener", "decision": "Shortlisted"}))
        S[f"cand_{n}"], S[f"app_{n}"] = c["id"], aid


def test_01_management_profile_and_dashboard():
    mg = sess(S["email_mg"])
    me = ok(mg.get(f"{API}/auth/me"))
    assert me["role"] == "management" and me["roles"] == ["management", "interviewer"]
    assert "Management" in me["role_label"] and "Interviewer" in me["role_label"]
    assert "feedback.submit" in me["permissions"] and "analytics.view" in me["permissions"]
    for p in ("req.manage", "cand.manage", "app.move", "offer.manage", "cost.manage", "joining.manage", "interview.manage", "users.manage", "selection.decide"):
        assert p not in me["permissions"], p
    a = ok(mg.get(f"{API}/analytics"))
    assert "kpis" in a and "funnel" in a
    assert mg.get(f"{API}/reports/pipeline", params={"format": "csv"}).status_code == 200


def test_02_selectable_as_interviewer(admin):
    assert S["m_mg"] and S["m_mg"]["active"] and S["m_mg"]["designation"] == "VP Engineering" and S["m_mg"]["role_label"] == "Management"
    iv = ok(admin.post(f"{API}/interviews", json={"application_id": S["app_one"], "round_name": "Leadership", "date": D(2), "start_time": "10:00",
                                                  "end_time": "11:00", "interviewer_ids": [S["m_mg"]["id"], S["m_iv"]["id"]], "force": True}))
    S["iv_mine"] = iv["id"]
    other = ok(admin.post(f"{API}/interviews", json={"application_id": S["app_two"], "round_name": "Tech", "date": D(2), "start_time": "12:00",
                                                     "end_time": "13:00", "interviewer_ids": [S["m_iv"]["id"]], "force": True}))
    S["iv_other"] = other["id"]


def test_03_sees_only_assigned_interviews():
    mg = sess(S["email_mg"])
    ids = [i["id"] for i in ok(mg.get(f"{API}/interviews"))]
    assert S["iv_mine"] in ids and S["iv_other"] not in ids
    assert ok(mg.get(f"{API}/interviews/{S['iv_mine']}"))["my_pending"] == [S["m_mg"]["id"]]
    denied(mg.get(f"{API}/interviews/{S['iv_other']}"))
    ok(mg.get(f"{API}/candidates/{S['cand_one']}"))  # candidate info for the interview
    mine = ok(mg.get(f"{API}/interviews", params={"mine": "true"}))
    assert [i["id"] for i in mine] == [S["iv_mine"]]
    # dashboards keep organisation-wide interview counts
    a = ok(mg.get(f"{API}/analytics", params={"requisition_id": S["req"]}))
    assert a["kpis"]["interviews_scheduled"] == 2


def test_04_submits_feedback():
    mg = sess(S["email_mg"])
    ok(mg.post(f"{API}/interviews/{S['iv_mine']}/feedback", json={"ratings": RATINGS, "recommendation": "Strong Hire", "detailed": "Clear leadership thinking"}))
    got = ok(mg.get(f"{API}/interviews/{S['iv_mine']}"))
    assert got["my_pending"] == [] and got["feedback_status"] == "Partial"
    assert mg.post(f"{API}/interviews/{S['iv_mine']}/feedback", json={"ratings": RATINGS, "recommendation": "Hire", "detailed": "again"}).status_code == 409
    denied(mg.post(f"{API}/interviews/{S['iv_other']}/feedback", json={"ratings": RATINGS, "recommendation": "Hire", "detailed": "x"}))
    # a management member who is not on the panel cannot give feedback for it
    denied(sess(S["email_mg2"]).post(f"{API}/interviews/{S['iv_mine']}/feedback", json={"ratings": RATINGS, "recommendation": "Hire", "detailed": "x"}))


def test_05_restrictions(admin):
    mg = sess(S["email_mg"])
    denied(mg.post(f"{API}/requisitions", json={"title": "x", "positions": 1}))
    denied(mg.put(f"{API}/requisitions/{S['req']}", json={"remarks": "x"}))
    denied(mg.put(f"{API}/candidates/{S['cand_one']}", json={"name": "Changed"}))
    denied(mg.post(f"{API}/candidates", json={"name": "x", "email": f"x_{TAG}@mms.test"}))
    denied(mg.post(f"{API}/applications/{S['app_one']}/status", json={"status": "Interview Completed"}))
    denied(mg.post(f"{API}/applications/{S['app_one']}/stage-reviews", json={"stage": "Screening", "date": D(1), "owner": "TEST_Screener", "decision": "Cleared"}))
    denied(mg.post(f"{API}/interviews/{S['iv_mine']}/status", json={"status": "Completed"}))  # status changes stay with Recruiters
    denied(mg.post(f"{API}/interviews", json={"application_id": S["app_one"], "round_name": "x", "date": D(1), "interviewer_ids": [S["m_mg"]["id"]]}))
    denied(mg.post(f"{API}/selections", json={"application_id": S["app_one"], "decision": "Selected", "selection_date": D(1), "decision_maker": "x"}))
    denied(mg.post(f"{API}/offers", json={"application_id": S["app_one"], "designation": "x", "ctc": 1, "validity_date": D(-5)}))
    denied(mg.post(f"{API}/costs", json={"category_id": "x", "amount": 1}))
    denied(mg.put(f"{API}/applications/{S['app_one']}/hire-cost", json={"ctc": 6, "consulting_fee": 0, "recruiter_fee": 0}))
    denied(mg.put(f"{API}/settings", json={"management_view_all_interviews": True}))
    assert ok(admin.get(f"{API}/candidates/{S['cand_one']}"))["name"] == f"TEST_MI one {TAG}"


def test_06_setting_allows_full_view(admin):
    ok(admin.put(f"{API}/settings", json={"management_view_all_interviews": True}))
    mg = sess(S["email_mg"])
    try:
        assert S["iv_other"] in [i["id"] for i in ok(mg.get(f"{API}/interviews"))]
        denied(mg.post(f"{API}/interviews/{S['iv_other']}/feedback", json={"ratings": RATINGS, "recommendation": "Hire", "detailed": "x"}))
    finally:
        ok(admin.put(f"{API}/settings", json={"management_view_all_interviews": False}))
    assert S["iv_other"] not in [i["id"] for i in ok(mg.get(f"{API}/interviews"))]


def test_07_other_roles_unchanged(admin):
    iv = sess(S["email_iv"])
    me = ok(iv.get(f"{API}/auth/me"))
    assert me["roles"] == ["interviewer"] and "analytics.view" not in me["permissions"]
    assert {i["id"] for i in ok(iv.get(f"{API}/interviews"))} == {S["iv_mine"], S["iv_other"]}
    ok(iv.post(f"{API}/interviews/{S['iv_mine']}/feedback", json={"ratings": RATINGS, "recommendation": "Hire", "detailed": "Good"}))
    assert ok(admin.get(f"{API}/interviews/{S['iv_mine']}"))["status"] == "Completed"
    rec = sess(S["email_rec"])
    me = ok(rec.get(f"{API}/auth/me"))
    assert me["roles"] == ["recruiter"] and {"req.manage", "app.move", "cost.manage", "interview.manage"} <= set(me["permissions"])
    assert len(ok(rec.get(f"{API}/interviews", params={"requisition_id": S["req"]}))) == 2
    ok(rec.put(f"{API}/requisitions/{S['req']}", json={"remarks": "still editable by Recruiter"}))


def test_08_role_change_hides_interviewer_record(admin):
    uid = S["user_mg2"]["id"]
    ok(admin.put(f"{API}/users/{uid}", json={"role": "recruiter"}))
    ms = ok(admin.get(f"{API}/masters"))
    m = next(x for x in ms if x["type"] == "interviewer" and x.get("user_id") == uid)
    assert m["active"] is False
    ok(admin.put(f"{API}/users/{uid}", json={"role": "management"}))
    m = next(x for x in ok(admin.get(f"{API}/masters")) if x["type"] == "interviewer" and x.get("user_id") == uid)
    assert m["active"] is True
