# Recruiter credit: an application is credited to the CANDIDATE's recruiter (requisition's only as a fallback),
# open applications follow later changes, closed ones keep their recruiter; plus the one-time correction script.
import os
import subprocess
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest
import requests
from pymongo import MongoClient

API = os.environ.get("API_URL", "http://localhost:8001").rstrip("/") + "/api"
ADMIN = {"email": os.environ.get("ADMIN_EMAIL", "").lower(), "password": os.environ.get("ADMIN_PASSWORD", "")}
TAG = uuid.uuid4().hex[:6]
D = lambda n: (date.today() - timedelta(days=n)).isoformat()
S = {}
assert any(h in os.environ.get("MONGO_URL", "") for h in ("127.0.0.1", "localhost")), "must run on a LOCAL database"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "mms_wf_test")]
BACKEND = Path(__file__).resolve().parent.parent


def ok(r):
    assert r.status_code == 200, f"{r.status_code}: {r.text}"
    return r.json()


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    s.headers["Authorization"] = "Bearer " + ok(s.post(f"{API}/auth/login", json=ADMIN))["access_token"]
    return s


def app_of(admin, cid):
    return [a for a in ok(admin.get(f"{API}/applications", params={"candidate_id": cid}))]


def test_00_setup(admin):
    for k in ("owner", "kalyani", "jaya"):
        S[k] = ok(admin.post(f"{API}/masters", json={"type": "recruiter", "name": f"TEST_RC {k} {TAG}"}))["id"]
    S["dept"] = ok(admin.post(f"{API}/masters", json={"type": "department", "name": f"TEST_RC Dept {TAG}"}))["id"]
    S["req"] = ok(admin.post(f"{API}/requisitions", json={"title": f"TEST_RC Architect {TAG}", "positions": 3, "crf_date": D(20), "status": "Open",
                                                           "recruiter_id": S["owner"], "department_id": S["dept"]}))["id"]
    mk = lambda n, rec: ok(admin.post(f"{API}/candidates", json={"name": f"TEST_RC {n} {TAG}", "email": f"rc_{n}_{TAG}@mms.test", "requisition_id": S["req"],
                                                                 **({"recruiter_id": rec} if rec else {}), "force": True}))["id"]
    S["c1"], S["c2"], S["c3"] = mk("one", S["kalyani"]), mk("two", S["jaya"]), mk("three", None)


def test_01_new_application_credits_candidate_recruiter(admin):
    assert app_of(admin, S["c1"])[0]["recruiter_id"] == S["kalyani"]
    assert app_of(admin, S["c2"])[0]["recruiter_id"] == S["jaya"]
    assert app_of(admin, S["c3"])[0]["recruiter_id"] == S["owner"]  # no candidate recruiter -> requisition's


def test_02_recruiter_performance_lists_each_recruiter(admin):
    d = ok(admin.get(f"{API}/analytics", params={"department_id": S["dept"]}))
    managed = {r["name"]: r["total"] for r in d["recruiters"]}
    assert managed == {f"TEST_RC kalyani {TAG}": 1, f"TEST_RC jaya {TAG}": 1, f"TEST_RC owner {TAG}": 1}


def test_03_open_applications_follow_changes_closed_keep(admin):
    closed = app_of(admin, S["c2"])[0]
    ok(admin.post(f"{API}/applications/{closed['id']}/status", json={"status": "CV Rejected", "reason": "Not a fit"}))
    ok(admin.put(f"{API}/candidates/{S['c1']}", json={"recruiter_id": S["jaya"]}))
    ok(admin.put(f"{API}/candidates/{S['c2']}", json={"recruiter_id": S["kalyani"]}))
    assert app_of(admin, S["c1"])[0]["recruiter_id"] == S["jaya"]     # open -> follows
    assert app_of(admin, S["c2"])[0]["recruiter_id"] == S["jaya"]     # closed -> keeps who handled it
    ok(admin.put(f"{API}/candidates/{S['c1']}", json={"recruiter_id": None}))
    assert app_of(admin, S["c1"])[0]["recruiter_id"] == S["owner"]    # cleared -> back to the requisition's


def run(*args):
    env = os.environ | {"PYTHONPATH": str(BACKEND)}
    return subprocess.run([sys.executable, "scripts/fix_application_recruiters.py", *args], cwd=BACKEND, env=env, capture_output=True, text=True)


def test_04_correction_script(admin, tmp_path):
    # simulate an application created under the old rule: credited to the requisition owner
    a3 = app_of(admin, S["c3"])[0]
    ok(admin.put(f"{API}/candidates/{S['c3']}", json={"recruiter_id": S["kalyani"]}))
    DB.applications.update_one({"id": a3["id"]}, {"$set": {"recruiter_id": S["owner"]}})
    a2 = app_of(admin, S["c2"])[0]  # closed one: candidate is Kalyani's, application still Jaya's
    preview = run()
    assert a3["code"] in preview.stdout and a2["code"] in preview.stdout and "Preview only" in preview.stdout
    n = int(preview.stdout.split("applications to update: ")[1].split()[0])
    assert run("--execute", "--database", DB.name, "--expect", str(n + 1), "--backup-dir", str(tmp_path)).returncode != 0
    assert DB.applications.find_one({"id": a3["id"]})["recruiter_id"] == S["owner"]  # refused -> unchanged
    r = run("--execute", "--database", DB.name, "--expect", str(n), "--backup-dir", str(tmp_path))
    assert r.returncode == 0 and f"Updated {n} application(s)." in r.stdout
    assert DB.applications.find_one({"id": a3["id"]})["recruiter_id"] == S["kalyani"]
    assert DB.applications.find_one({"id": a2["id"]})["recruiter_id"] == S["kalyani"]  # past results corrected too
    assert "Nothing to change" in run().stdout
    backup = next(tmp_path.glob("*_app_recruiters_*.json"))
    assert run("--restore", str(backup), "--database", DB.name).returncode == 0
    assert DB.applications.find_one({"id": a3["id"]})["recruiter_id"] == S["owner"]
    run("--execute", "--database", DB.name, "--expect", str(n), "--backup-dir", str(tmp_path))  # leave the test DB corrected
