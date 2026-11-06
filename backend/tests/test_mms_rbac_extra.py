# MMS extra regression: brute-force lockout, transitions matrix, offer decline/revoke reasons, RBAC edge cases
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "anastaibani53@gmail.com", "password": "MMS@Admin2026"}
PW = "TestPass@123"


def sess(email=None, pw=PW):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw} if email else ADMIN)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def ctx():
    a = sess()
    c = {"a": a}
    for role, n in [("recruiter", "rx"), ("recruiter", "ry"), ("interviewer", "ix"), ("interviewer", "iy"), ("hiring_manager", "hx")]:
        r = a.post(f"{API}/users", json={"email": f"test_{n}@mms.test", "name": f"TEST_{n}", "role": role, "password": PW})
        assert r.status_code == 200, r.text
        c[n] = r.json()["id"]
    ms = a.get(f"{API}/masters").json()
    for n in ["rx", "ry", "ix", "iy", "hx"]:
        c["m_" + n] = next(m["id"] for m in ms if m.get("user_id") == c[n])
    c["reqx"] = a.post(f"{API}/requisitions", json={"title": "TEST_RX", "positions": 1, "recruiter_id": c["m_rx"], "hiring_manager_id": c["m_hx"]}).json()["id"]
    c["reqy"] = a.post(f"{API}/requisitions", json={"title": "TEST_RY", "positions": 1, "recruiter_id": c["m_ry"]}).json()["id"]
    c["cx"] = a.post(f"{API}/candidates", json={"name": "TEST_CX", "email": "test_cx@mms.test", "requisition_id": c["reqx"]}).json()["id"]
    c["cy"] = a.post(f"{API}/candidates", json={"name": "TEST_CY", "email": "test_cy@mms.test", "requisition_id": c["reqy"]}).json()["id"]
    apps = a.get(f"{API}/applications").json()
    c["ax"] = next(x["id"] for x in apps if x["candidate_id"] == c["cx"])
    c["ay"] = next(x["id"] for x in apps if x["candidate_id"] == c["cy"])
    return c


def test_lockout():
    for _ in range(5):
        requests.post(f"{API}/auth/login", json={"email": "test_lock@mms.test", "password": "bad"})
    r = requests.post(f"{API}/auth/login", json={"email": "test_lock@mms.test", "password": "bad"})
    assert r.status_code == 429


def test_recruiter_cannot_touch_others(ctx):
    rx = sess("test_rx@mms.test")
    assert rx.get(f"{API}/requisitions/{ctx['reqy']}").status_code == 404
    assert rx.put(f"{API}/requisitions/{ctx['reqy']}", json={"remarks": "hack"}).status_code in (403, 404)
    assert rx.get(f"{API}/candidates/{ctx['cy']}").status_code == 404
    assert rx.get(f"{API}/applications/{ctx['ay']}").status_code == 404
    assert rx.post(f"{API}/applications/{ctx['ay']}/status", json={"status": "Screening"}).status_code == 404
    assert rx.get(f"{API}/requisitions/{ctx['reqx']}").json()["id"] == ctx["reqx"]


def test_hm_selected(ctx):
    hx = sess("test_hx@mms.test")
    r = hx.post(f"{API}/applications/{ctx['ax']}/status", json={"status": "Selected"})
    assert r.status_code == 200, r.text
    assert hx.post(f"{API}/applications/{ctx['ay']}/status", json={"status": "Shortlisted"}).status_code == 404


def test_offer_decline_revoke_reason(ctx):
    a = ctx["a"]
    o = a.post(f"{API}/offers", json={"application_id": ctx["ax"], "designation": "X", "ctc": 5, "validity_date": "2026-03-01"}).json()
    for act in ["submit", "approve"]:
        assert a.post(f"{API}/offers/{o['id']}/action", json={"action": act}).status_code == 200
    assert a.post(f"{API}/offers/{o['id']}/action", json={"action": "revoke"}).status_code == 400
    assert a.post(f"{API}/offers/{o['id']}/action", json={"action": "decline", "reason": "  "}).status_code == 400
    r = a.post(f"{API}/offers/{o['id']}/action", json={"action": "decline", "reason": "Better offer"})
    assert r.status_code == 200 and r.json()["status"] == "Declined"
    assert a.get(f"{API}/applications/{ctx['ax']}").json()["status"] == "Offer Declined"


def test_transitions_matrix(ctx):
    a = ctx["a"]
    meta = a.get(f"{API}/meta").json()
    orig = meta["settings"]["transitions"]
    t = {k: list(v) for k, v in orig.items()}
    t["New"] = [s for s in t["New"] if s != "Shortlisted"]
    try:
        assert a.put(f"{API}/settings", json={"transitions": t}).status_code == 200
        r = a.post(f"{API}/applications/{ctx['ay']}/status", json={"status": "Shortlisted"})
        assert r.status_code == 400 and "not permitted" in r.text
        assert a.post(f"{API}/applications/{ctx['ay']}/status", json={"status": "Screening"}).status_code == 200
    finally:
        a.put(f"{API}/settings", json={"transitions": orig})


def test_interviewer_filter_leak(ctx):
    a = ctx["a"]
    r = a.post(f"{API}/interviews", json={"application_id": ctx["ay"], "round_name": "R1", "date": "2026-03-01",
                                          "start_time": "10:00", "end_time": "11:00", "interviewer_ids": [ctx["m_iy"]]})
    assert r.status_code == 200, r.text
    ix = sess("test_ix@mms.test")
    assert ix.get(f"{API}/interviews").json() == []
    leaked = ix.get(f"{API}/interviews", params={"interviewer_id": ctx["m_iy"]}).json()
    assert leaked == [], f"interviewer sees others' interviews via interviewer_id filter: {len(leaked)}"


def test_management_post_403():
    a = sess()
    a.post(f"{API}/users", json={"email": "test_mg2@mms.test", "name": "TEST_mg2", "role": "management", "password": PW})
    mg = sess("test_mg2@mms.test")
    assert mg.post(f"{API}/costs", json={"amount": 1}).status_code == 403
    assert mg.post(f"{API}/interviews", json={}).status_code == 403
    assert mg.post(f"{API}/offers", json={}).status_code == 403
    assert mg.get(f"{API}/analytics").status_code == 200
