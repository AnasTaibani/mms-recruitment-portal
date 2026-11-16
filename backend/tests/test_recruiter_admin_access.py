# Recruiters manage Users & Roles and Master Data & Settings, but never Super Admin accounts, the Activity Log,
# data cleanup or data migrations.
import os
import uuid

import pytest
import requests

API = os.environ.get("API_URL", "http://localhost:8001").rstrip("/") + "/api"
ADMIN = {"email": os.environ.get("ADMIN_EMAIL", "").lower(), "password": os.environ.get("ADMIN_PASSWORD", "")}
PW = "TestPass@123"
TAG = uuid.uuid4().hex[:6]


def login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = "Bearer " + r.json()["access_token"]
    return s, r.json()


@pytest.fixture(scope="module")
def ctx():
    admin, me = login(ADMIN["email"], ADMIN["password"])
    email = f"ra_rec_{TAG}@mms.test"
    rid = admin.post(f"{API}/users", json={"email": email, "name": f"TEST_RA Recruiter {TAG}", "role": "recruiter", "password": PW}).json()["id"]
    rec, rec_user = login(email, PW)
    return {"admin": admin, "admin_id": me["id"], "rec": rec, "rec_id": rid, "rec_user": rec_user}


def test_recruiter_sees_the_permissions(ctx):
    perms = set(ctx["rec_user"]["permissions"])
    assert {"users.manage", "masters.manage", "settings.manage"} <= perms
    assert not perms & {"users.super", "activity.view"}


def test_recruiter_manages_users(ctx):
    rec = ctx["rec"]
    assert rec.get(f"{API}/users").status_code == 200
    r = rec.post(f"{API}/users", json={"email": f"ra_iv_{TAG}@mms.test", "name": f"TEST_RA Interviewer {TAG}", "role": "interviewer", "password": PW})
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    assert rec.put(f"{API}/users/{uid}", json={"role": "management"}).status_code == 200
    assert rec.post(f"{API}/users/{uid}/reset-password", json={"password": "Another@1234"}).status_code == 200
    assert rec.put(f"{API}/users/{ctx['rec_id']}", json={"role": "interviewer"}).status_code == 400  # not their own role


def test_recruiter_cannot_touch_super_admins(ctx):
    rec = ctx["rec"]
    assert rec.post(f"{API}/users", json={"email": f"ra_sa_{TAG}@mms.test", "name": f"TEST_RA Super {TAG}", "role": "super_admin", "password": PW}).status_code == 403
    others = [u for u in rec.get(f"{API}/users").json() if u["role"] != "super_admin"]
    assert rec.put(f"{API}/users/{others[0]['id']}", json={"role": "super_admin"}).status_code == 403
    assert rec.put(f"{API}/users/{ctx['admin_id']}", json={"name": "Changed"}).status_code == 403
    assert rec.post(f"{API}/users/{ctx['admin_id']}/reset-password", json={"password": "Hijack@1234"}).status_code == 403


def test_recruiter_manages_masters_and_settings(ctx):
    rec = ctx["rec"]
    r = rec.post(f"{API}/masters", json={"type": "department", "name": f"TEST_RA Dept {TAG}"})
    assert r.status_code == 200, r.text
    assert rec.put(f"{API}/masters/{r.json()['id']}", json={"name": f"TEST_RA Dept renamed {TAG}"}).status_code == 200
    cur = ctx["admin"].get(f"{API}/meta").json()["settings"]
    assert rec.put(f"{API}/settings", json={"stale_days": cur.get("stale_days") or 14}).status_code == 200


def test_still_super_admin_only(ctx):
    rec = ctx["rec"]
    assert rec.get(f"{API}/activity").status_code == 403
    assert rec.get(f"{API}/admin/data-status").status_code in (403, 404)
    for path in ("/admin/migrations/joined-to-screening/preview",):
        assert rec.get(f"{API}{path}").status_code in (403, 404, 405)


def test_interviewer_cannot_see_requisitions_or_candidates(ctx):
    admin = ctx["admin"]
    email = f"ra_ivonly_{TAG}@mms.test"
    admin.post(f"{API}/users", json={"email": email, "name": f"TEST_RA Interviewer Only {TAG}", "role": "interviewer", "password": PW})
    iv, me = login(email, PW)
    assert not {"req.view", "cand.view"} & set(me["permissions"])
    for path in ("/requisitions", "/candidates", "/applications", "/candidates/check-duplicates?email=a@b.c"):
        assert iv.get(f"{API}{path}").status_code == 403, path
    any_req = admin.get(f"{API}/requisitions").json()[0]["id"]
    any_cand = admin.get(f"{API}/candidates").json()[0]["id"]
    assert iv.get(f"{API}/requisitions/{any_req}").status_code == 403
    assert iv.get(f"{API}/candidates/{any_cand}").status_code == 403
    assert iv.get(f"{API}/interviews").status_code == 200  # their own interviews still work
    # Management and Recruiters, who also interview, keep their own access
    rec = ctx["rec"]
    assert rec.get(f"{API}/requisitions").status_code == 200 and rec.get(f"{API}/candidates").status_code == 200
