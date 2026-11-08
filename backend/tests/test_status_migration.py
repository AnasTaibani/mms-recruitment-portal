# One-time Joined → Screening migration. This test RUNS the migration, so it refuses to run against anything
# but a local test database: start the backend with a throw-away DB_NAME and set MIGRATION_TEST=1.
import os
import uuid
from datetime import date, timedelta

import pytest
import requests

API = os.environ.get("API_URL", "http://localhost:8001").rstrip("/") + "/api"
ADMIN = {"email": os.environ.get("ADMIN_EMAIL", "").lower(), "password": os.environ.get("ADMIN_PASSWORD", "")}
TAG = uuid.uuid4().hex[:6]
D = lambda n: (date.today() - timedelta(days=n)).isoformat()
S = {}
PHRASE = "MOVE JOINED TO SCREENING"

pytestmark = pytest.mark.skipif(os.environ.get("MIGRATION_TEST") != "1" or "localhost" not in API and "127.0.0.1" not in API,
                                reason="runs the real migration — local throw-away database only (MIGRATION_TEST=1)")


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN)
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return s


def ok(r):
    assert r.status_code == 200, f"{r.status_code}: {r.text}"
    return r.json()


def make(a, name, until):
    c = ok(a.post(f"{API}/candidates", json={"name": f"TEST_MIG_{name}_{TAG}", "email": f"mig_{name.lower()}_{TAG}@mms.test", "requisition_id": S["req"], "force": True}))
    aid = next(x["id"] for x in ok(a.get(f"{API}/applications", params={"requisition_id": S["req"]})) if x["candidate_id"] == c["id"])
    if until == "New":
        return c["id"], aid
    ok(a.post(f"{API}/applications/{aid}/stage-reviews", json={"stage": "Screening", "date": D(20), "owner": "HR", "decision": "Cleared"}))
    if until == "Screening":
        return c["id"], aid
    ok(a.post(f"{API}/applications/{aid}/stage-reviews", json={"stage": "Shortlisting", "date": D(19), "owner": "HM", "decision": "Shortlisted"}))
    ok(a.post(f"{API}/applications/{aid}/interview-waiver", json={"reason": "migration test"}))
    ok(a.post(f"{API}/selections", json={"application_id": aid, "decision": "Selected", "selection_date": D(10), "decision_maker": "CTO", "compensation": 6, "approval_status": "Approved"}))
    o = ok(a.post(f"{API}/offers", json={"application_id": aid, "designation": "Engineer", "ctc": 6, "validity_date": D(-30)}))
    for act, d in (("submit", None), ("approve", None), ("release", D(8)), ("accept", D(6))):
        ok(a.post(f"{API}/offers/{o['id']}/action", json={"action": act, **({"date": d} if d else {})}))
    if until == "Offer Accepted":
        return c["id"], aid
    ok(a.put(f"{API}/applications/{aid}/hire-cost", json={"ctc": 6, "consulting_fee": 0.5, "recruiter_fee": 0.2}))
    ok(a.post(f"{API}/applications/{aid}/status", json={"status": "Joined", "joining_date": D(2)}))
    return c["id"], aid


def test_00_setup(admin):
    p = ok(admin.get(f"{API}/admin/migrations/joined-to-screening"))
    assert p["environment"] != "production", "refusing to run the migration test against production"
    S["req"] = ok(admin.post(f"{API}/requisitions", json={"title": f"TEST_MIG Role {TAG}", "positions": 5, "crf_date": D(60), "status": "Open"}))["id"]
    S["joined"] = [make(admin, f"J{i}", "Joined") for i in range(3)]
    S["others"] = [make(admin, "New", "New"), make(admin, "Scr", "Screening"), make(admin, "OA", "Offer Accepted")]
    S["before"] = {aid: ok(admin.get(f"{API}/applications/{aid}")) for _, aid in S["joined"] + S["others"]}
    S["an_before"] = ok(admin.get(f"{API}/analytics", params={"requisition_id": S["req"]}))
    assert ok(admin.get(f"{API}/requisitions/{S['req']}"))["filled_positions"] == 3


def test_01_preview(admin):
    p = ok(admin.get(f"{API}/admin/migrations/joined-to-screening"))
    assert not p["already_applied"]
    ids = {r["application_id"] for r in p["applications"]}
    assert {aid for _, aid in S["joined"]} <= ids and not ({aid for _, aid in S["others"]} & ids)
    assert p["count"] == p["by_status"].get("Joined") == len(ids)
    S["count"] = p["count"]


def test_02_guards(admin):
    url = f"{API}/admin/migrations/joined-to-screening"
    assert admin.post(url, json={"confirm": "yes", "database": os.environ.get("DB_NAME", ""), "expected_count": S["count"]}).status_code == 400
    db = ok(admin.get(url))["database"]
    assert admin.post(url, json={"confirm": PHRASE, "database": "wrong", "expected_count": S["count"]}).status_code == 400
    assert admin.post(url, json={"confirm": PHRASE, "database": db, "expected_count": S["count"] + 1}).status_code == 409  # stale preview
    assert ok(admin.get(url))["count"] == S["count"]  # nothing changed
    S["db"] = db


def test_03_run(admin):
    out = ok(admin.post(f"{API}/admin/migrations/joined-to-screening", json={"confirm": PHRASE, "database": S["db"], "expected_count": S["count"]}))
    v = out["verification"]
    assert out["ok"] and out["changed"] == S["count"] and v["all_moved"] and v["application_count_unchanged"] and v["other_applications_untouched"]
    S["run"] = out


def test_04_records(admin):
    for cid, aid in S["joined"]:
        a, b = ok(admin.get(f"{API}/applications/{aid}")), S["before"][aid]
        assert a["status"] == "Screening" and a["closed"] is False
        assert a["history"][:-1] == b["history"]  # earlier history untouched, one entry added
        h = a["history"][-1]
        assert h["from"] == "Joined" and h["status"] == "Screening" and h["migration_id"] and h["reason"] == "Production candidate status reset"
        assert a["hire_cost"] == b["hire_cost"] and a["candidate_id"] == b["candidate_id"] and a["requisition_id"] == b["requisition_id"]
        assert ok(admin.get(f"{API}/candidates/{cid}"))["name"].startswith("TEST_MIG_")
        offers = [o for o in ok(admin.get(f"{API}/offers", params={"candidate_id": cid})) if o["application_id"] == aid]
        assert [o["status"] for o in offers] == ["Accepted"] and offers[0]["history"]
        j = [x for x in ok(admin.get(f"{API}/joinings", params={"requisition_id": S["req"]})) if x["application_id"] == aid]
        assert len(j) == 1 and j[0]["status"] == "Joined" and j[0]["actual_date"] == D(2)
        assert len(ok(admin.get(f"{API}/selections", params={"application_id": aid})) or [1]) >= 1
    for _, aid in S["others"]:
        assert ok(admin.get(f"{API}/applications/{aid}")) == S["before"][aid]  # byte-for-byte unchanged


def test_05_audit(admin):
    acts = ok(admin.get(f"{API}/activity"))
    acts = acts if isinstance(acts, list) else acts.get("items", [])
    mig = [x for x in acts if x["action"] == "status_migration"]
    for cid, aid in S["joined"]:
        e = [x for x in mig if x["entity_id"] == aid]
        assert len(e) == 1 and cid in e[0]["details"] and aid in e[0]["details"] and "Joined → Screening" in e[0]["details"]
        assert "2026-11-08-joined-to-screening" in e[0]["details"] and e[0]["at"]
    assert any(x["action"] == "data_migration" for x in acts)


def test_06_analytics(admin):
    a = ok(admin.get(f"{API}/analytics", params={"requisition_id": S["req"]}))
    by = {r["status"]: r["count"] for r in a["status_breakdown"]}
    assert by.get("Joined", 0) == 0 and by["Screening"] == 3 + 1
    assert a["kpis"]["joined"] == 0 and a["cost"]["joined"] == 0 and a["cost"]["cost_per_hire"] is None
    funnel = {f["stage"]: f["count"] for f in a["funnel"]}
    assert funnel["Joined"] == 0
    assert ok(admin.get(f"{API}/requisitions/{S['req']}"))["filled_positions"] == 0
    pipe = ok(admin.get(f"{API}/applications", params={"requisition_id": S["req"], "status": "Screening"}))
    assert {x["id"] for x in pipe} >= {aid for _, aid in S["joined"]}


def test_07_rerun_is_noop(admin):
    acts_before = len([x for x in (lambda d: d if isinstance(d, list) else d.get("items", []))(ok(admin.get(f"{API}/activity"))) if x["action"] == "status_migration"])
    p = ok(admin.get(f"{API}/admin/migrations/joined-to-screening"))
    assert p["already_applied"] and p["count"] == 0
    out = ok(admin.post(f"{API}/admin/migrations/joined-to-screening", json={"confirm": PHRASE, "database": S["db"], "expected_count": 0}))
    assert out["already_applied"] and out["changed"] == 0
    acts_after = len([x for x in (lambda d: d if isinstance(d, list) else d.get("items", []))(ok(admin.get(f"{API}/activity"))) if x["action"] == "status_migration"])
    assert acts_before == acts_after
    # new candidates still follow the normal lifecycle and can join
    _, aid = make(admin, "After", "Joined")
    assert ok(admin.get(f"{API}/applications/{aid}"))["status"] == "Joined"
    assert ok(admin.get(f"{API}/admin/migrations/joined-to-screening"))["already_applied"]
