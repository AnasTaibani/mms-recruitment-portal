# Executive dashboard API — figures must match the underlying records, respect roles, never invent comparisons.
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


def hero(d, key):
    return next(h for h in d["hero"] if h["key"] == key)


def test_00_setup(admin):
    dept = ok(admin.post(f"{API}/masters", json={"type": "department", "name": f"TEST_Dash Dept {TAG}"}))
    S["dept"] = dept["id"]
    S["req"] = ok(admin.post(f"{API}/requisitions", json={"title": f"TEST_Dash Role {TAG}", "positions": 3, "crf_date": D(40), "status": "Open", "department_id": dept["id"]}))["id"]
    for role, key in (("management", "mg"), ("interviewer", "iv"), ("recruiter", "rec")):
        S[f"email_{key}"] = f"dash_{key}_{TAG}@mms.test"
        ok(admin.post(f"{API}/users", json={"email": S[f"email_{key}"], "name": f"TEST_dash_{key}_{TAG}", "role": role, "password": PW}))
    apps = []
    for n in range(3):
        c = ok(admin.post(f"{API}/candidates", json={"name": f"TEST_Dash {n} {TAG}", "email": f"dash_{n}_{TAG}@mms.test", "requisition_id": S["req"], "force": True}))
        apps.append(next(x["id"] for x in ok(admin.get(f"{API}/applications", params={"requisition_id": S["req"]})) if x["candidate_id"] == c["id"]))
    ok(admin.post(f"{API}/applications/{apps[0]}/stage-reviews", json={"stage": "Screening", "date": D(1), "owner": "HR", "decision": "Cleared"}))
    ok(admin.post(f"{API}/applications/{apps[1]}/stage-reviews", json={"stage": "Screening", "date": D(1), "owner": "HR", "decision": "Cleared"}))
    ok(admin.post(f"{API}/applications/{apps[1]}/stage-reviews", json={"stage": "Shortlisting", "date": D(1), "owner": "HM", "decision": "Shortlisted"}))
    S["apps"] = apps


def test_01_numbers_match_records(admin):
    d = ok(admin.get(f"{API}/dashboard", params={"period": "30d", "department_id": S["dept"]}))
    assert hero(d, "candidates")["value"] == 3 and hero(d, "candidates")["period_count"] == 3
    assert hero(d, "screening")["value"] == 1  # one still in Screening, one moved on to Shortlisted
    assert hero(d, "screening")["period_count"] == 2
    assert hero(d, "open_requisitions")["value"] == 1 and hero(d, "hires")["value"] == 0
    for k in ("candidates", "screening", "hires"):
        h = hero(d, k)
        assert h["previous_count"] == 0 and h["change_pct"] is None  # never invented
    pts = d["trend"]["points"]
    assert sum(p["added"] for p in pts) == 3 and sum(p["shortlisted"] for p in pts) == 1
    st = {s["stage"]: s["count"] for s in d["funnel"]["stages"]}
    assert st["New"] == 3 and st["Screening"] == 2 and st["Shortlisted"] == 1 and st["Joined"] == 0
    assert d["funnel"]["cohort"] == 3 and d["funnel"]["overall_conversion"] == 0
    counts = [s["count"] for s in d["funnel"]["stages"][:-1]]
    assert counts == sorted(counts, reverse=True)
    dist = {x["status"]: x["count"] for x in d["distribution"]}
    assert dist == {"New": 1, "Screening": 1, "Shortlisted": 1} and d["total_applications"] == 3
    pend = {p["key"]: p for p in d["pending"]}
    assert pend["to_schedule"]["count"] == 1 and pend["to_schedule"]["link"] == "/pipeline?status=Shortlisted"
    assert d["requisitions"]["positions"] == 3 and d["requisitions"]["open"] == 1 and d["requisitions"]["remaining"] == 3
    assert d["cost"]["cost_per_hire"] is None and d["age_per_hire"]["completed"]["avg"] is None
    assert any(a["event"] == "Candidate shortlisted" for a in d["activity"])


def test_02_consistent_with_analytics(admin):
    d = ok(admin.get(f"{API}/dashboard", params={"period": "year"}))
    a = ok(admin.get(f"{API}/analytics", params={"date_from": d["period"]["start"], "date_to": d["period"]["end"]}))
    assert d["cost"]["cost_per_hire"] == a["cost"]["cost_per_hire"] and d["cost"]["total"] == a["cost"]["total"]
    assert d["age_per_hire"]["completed"] == a["aph"]["completed"]
    assert sum(s["candidates"] for s in d["sources"]) == sum(s["total"] for s in a["sources"])
    assert {r["name"]: r["joined"] for r in d["recruiters"]} == {r["name"]: r["joined"] for r in a["recruiters"]}


def test_03_periods_and_validation(admin):
    for p in ("7d", "30d", "90d", "quarter", "year"):
        d = ok(admin.get(f"{API}/dashboard", params={"period": p}))
        s, e, ps, pe = (date.fromisoformat(d["period"][k]) for k in ("start", "end", "previous_start", "previous_end"))
        assert (e - s) == (pe - ps) and pe == s - timedelta(days=1)
    d = ok(admin.get(f"{API}/dashboard", params={"period": "custom", "date_from": D(10), "date_to": D(0), "granularity": "month"}))
    assert d["period"]["granularity"] == "month" and all(len(p["bucket"]) == 7 for p in d["trend"]["points"])
    assert admin.get(f"{API}/dashboard", params={"period": "custom"}).status_code == 400
    assert admin.get(f"{API}/dashboard", params={"period": "custom", "date_from": D(0), "date_to": D(5)}).status_code == 400
    assert admin.get(f"{API}/dashboard", params={"period": "forever"}).status_code == 400


def test_04_roles(admin):
    assert sess(S["email_iv"]).get(f"{API}/dashboard").status_code == 403
    mg = ok(sess(S["email_mg"]).get(f"{API}/dashboard", params={"period": "30d", "department_id": S["dept"]}))
    assert hero(mg, "candidates")["value"] == 3 and mg["cost"] is not None  # management: read-only org view
    assert mg["upcoming_interviews"] == []  # only interviews they are assigned to
    rec = ok(sess(S["email_rec"]).get(f"{API}/dashboard", params={"period": "30d", "department_id": S["dept"]}))
    assert hero(rec, "candidates")["value"] == 3
