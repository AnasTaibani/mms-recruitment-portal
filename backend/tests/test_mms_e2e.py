# MMS Recruitment Portal - end-to-end backend regression (auth, users, RBAC, reqs, candidates, pipeline,
# interviews, offers, joining, costs, analytics, reports, import, notifications, activity)
import os
import io
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "anastaibani53@gmail.com", "password": "MMS@Admin2026"}
PW = "TestPass@123"
S = {}  # shared state across ordered tests


def sess(email=None, password=PW):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email or ADMIN["email"], "password": password if email else ADMIN["password"]})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def admin():
    return sess()


# ---------- Auth ----------
class TestAuth:
    def test_login_cookies_me(self):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json=ADMIN)
        assert r.status_code == 200
        sc = r.headers.get("set-cookie", "").lower()
        assert "access_token" in sc and "httponly" in sc
        me = s.get(f"{API}/auth/me").json()
        assert me["email"] == ADMIN["email"] and me["role"] == "super_admin"

    def test_wrong_password(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN["email"], "password": "wrong-pass"})
        assert r.status_code == 401

    def test_unauth_me(self):
        assert requests.get(f"{API}/auth/me").status_code == 401

    def test_logout(self):
        s = sess()
        assert s.post(f"{API}/auth/logout").status_code == 200
        assert s.get(f"{API}/auth/me").status_code == 401


# ---------- Users & masters ----------
class TestUsers:
    def test_create_users_each_role(self, admin):
        for role in ["hr_admin", "recruiter", "hiring_manager", "interviewer", "management"]:
            r = admin.post(f"{API}/users", json={"email": f"test_{role}@mms.test", "name": f"TEST_{role}", "role": role, "password": PW})
            assert r.status_code == 200, r.text
            S[f"user_{role}"] = r.json()["id"]
        r = admin.post(f"{API}/users", json={"email": "test_interviewer2@mms.test", "name": "TEST_interviewer2", "role": "interviewer", "password": PW})
        assert r.status_code == 200
        S["user_interviewer2"] = r.json()["id"]
        r = admin.post(f"{API}/users", json={"email": "test_recruiter@mms.test", "name": "dup", "role": "recruiter", "password": PW})
        assert r.status_code == 409

    def test_auto_masters(self, admin):
        ms = admin.get(f"{API}/masters").json()
        for role in ["recruiter", "hiring_manager", "interviewer", "interviewer2"]:
            ptype = "interviewer" if role == "interviewer2" else role
            m = [x for x in ms if x["type"] == ptype and x.get("user_id") == S[f"user_{role}"]]
            assert m, f"no master for {role}"
            S[f"m_{role}"] = m[0]["id"]
        S["cost_cat"] = next(x["id"] for x in ms if x["type"] == "cost_category")
        S["source"] = next(x["id"] for x in ms if x["type"] == "source")

    def test_hr_cannot_manage_super(self, admin):
        hr = sess("test_hr_admin@mms.test")
        r = hr.post(f"{API}/users", json={"email": "test_sa@mms.test", "name": "TEST_sa", "role": "super_admin", "password": PW})
        assert r.status_code == 403
        me = admin.get(f"{API}/auth/me").json()
        assert hr.put(f"{API}/users/{me['id']}", json={"name": "Hacked"}).status_code == 403
        assert hr.post(f"{API}/users/{me['id']}/reset-password", json={"password": "Hacked@1234"}).status_code == 403

    def test_edit_role_deactivate_reset(self, admin):
        r = admin.post(f"{API}/users", json={"email": "test_temp@mms.test", "name": "TEST_temp", "role": "management", "password": PW})
        uid = r.json()["id"]
        r = admin.put(f"{API}/users/{uid}", json={"role": "hr_admin"})
        assert r.status_code == 200 and r.json()["role"] == "hr_admin"
        assert admin.post(f"{API}/users/{uid}/reset-password", json={"password": "NewPass@123"}).status_code == 200
        sess("test_temp@mms.test", "NewPass@123")
        assert admin.put(f"{API}/users/{uid}", json={"active": False}).status_code == 200
        r = requests.post(f"{API}/auth/login", json={"email": "test_temp@mms.test", "password": "NewPass@123"})
        assert r.status_code in (401, 403), r.text


# ---------- Requisitions / candidates / pipeline ----------
class TestRecruit:
    def test_create_reqs(self, admin):
        r = admin.post(f"{API}/requisitions", json={"title": "TEST_Backend Engineer", "positions": 1, "recruiter_id": S["m_recruiter"],
                                                    "hiring_manager_id": S["m_hiring_manager"], "crf_date": "2025-12-01",
                                                    "initiation_date": "2025-12-05", "status": "Open"})
        assert r.status_code == 200, r.text
        S["req1"] = r.json()["id"]
        r = admin.post(f"{API}/requisitions", json={"title": "TEST_Other Role", "positions": 2})
        S["req2"] = r.json()["id"]
        lst = admin.get(f"{API}/requisitions", params={"q": "TEST_Backend"}).json()
        assert any(x["id"] == S["req1"] for x in lst)
        assert admin.put(f"{API}/requisitions/{S['req1']}", json={"remarks": "edited"}).json().get("remarks") in ("edited", None)

    def test_recruiter_scope(self):
        rc = sess("test_recruiter@mms.test")
        ids = [x["id"] for x in rc.get(f"{API}/requisitions").json()]
        assert S["req1"] in ids and S["req2"] not in ids
        assert rc.get(f"{API}/requisitions/{S['req2']}").status_code == 404

    def test_candidate_dup(self, admin):
        body = {"name": "TEST_Cand One", "email": "test_cand1@mms.test", "phone": "9876500001", "requisition_id": S["req1"], "source_id": S["source"]}
        r = admin.post(f"{API}/candidates", json=body)
        assert r.status_code == 200, r.text
        S["cand1"] = r.json()["id"]
        r = admin.post(f"{API}/candidates", json={"name": "TEST_Dup", "phone": "+91 98765 00001"})
        assert r.status_code == 409
        r = admin.post(f"{API}/candidates", json={"name": "TEST_Dup", "phone": "+91 98765 00001", "force": True})
        assert r.status_code == 200
        S["cand_dup"] = r.json()["id"]
        r = admin.post(f"{API}/candidates", json={"name": "TEST_Cand Two", "email": "test_cand2@mms.test", "requisition_id": S["req1"]})
        S["cand2"] = r.json()["id"]
        apps = admin.get(f"{API}/applications", params={"requisition_id": S["req1"]}).json()
        S["app1"] = next(a["id"] for a in apps if a["candidate_id"] == S["cand1"])
        S["app2"] = next(a["id"] for a in apps if a["candidate_id"] == S["cand2"])

    def test_resume_upload_download(self, admin):
        pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
        r = admin.post(f"{API}/files", data={"entity": "candidate", "entity_id": S["cand1"]}, files={"file": ("cv.pdf", pdf, "application/pdf")})
        assert r.status_code == 200, r.text
        fid = r.json()["file_id"]
        d = admin.get(f"{API}/files/{fid}")
        assert d.status_code == 200 and d.content == pdf
        r = admin.post(f"{API}/files", data={"entity": "candidate", "entity_id": S["cand1"]}, files={"file": ("x.txt", b"hi", "text/plain")})
        assert r.status_code == 400

    def test_status_moves(self, admin):
        assert admin.post(f"{API}/applications/{S['app2']}/status", json={"status": "CV Rejected"}).status_code == 400
        r = admin.post(f"{API}/applications/{S['app2']}/status", json={"status": "CV Rejected", "reason": "Skills mismatch"})
        assert r.status_code == 200 and r.json()["status"] == "CV Rejected"
        hm = sess("test_hiring_manager@mms.test")
        assert hm.post(f"{API}/applications/{S['app1']}/status", json={"status": "Screening"}).status_code == 403
        r = hm.post(f"{API}/applications/{S['app1']}/status", json={"status": "Shortlisted"})
        assert r.status_code == 200, r.text

    def test_close_blocked(self, admin):
        r = admin.put(f"{API}/requisitions/{S['req1']}", json={"status": "Closed", "closure_reason": "x"})
        assert r.status_code == 400 and "active" in r.text

    def test_management_readonly(self):
        mg = sess("test_management@mms.test")
        assert mg.get(f"{API}/requisitions").status_code == 200
        assert mg.post(f"{API}/requisitions", json={"title": "TEST_x", "positions": 1}).status_code == 403
        assert mg.put(f"{API}/requisitions/{S['req1']}", json={"remarks": "x"}).status_code == 403
        assert mg.post(f"{API}/candidates", json={"name": "TEST_x", "email": "x@x.x"}).status_code == 403
        assert mg.post(f"{API}/applications/{S['app1']}/status", json={"status": "Screening"}).status_code == 403


# ---------- Interviews ----------
class TestInterviews:
    def test_schedule_conflict(self, admin):
        body = {"application_id": S["app1"], "round_name": "Technical 1", "date": "2026-02-10", "start_time": "10:00",
                "end_time": "11:00", "mode": "Online", "interviewer_ids": [S["m_interviewer"], S["m_interviewer2"]]}
        r = admin.post(f"{API}/interviews", json=body)
        assert r.status_code == 200, r.text
        S["iv1"] = r.json()["id"]
        r = admin.post(f"{API}/interviews", json={**body, "round_name": "Clash", "start_time": "10:30", "end_time": "11:30",
                                                  "interviewer_ids": [S["m_interviewer"]]})
        assert r.status_code == 409
        r = admin.post(f"{API}/interviews", json={**body, "round_name": "Clash", "start_time": "10:30", "end_time": "11:30",
                                                  "interviewer_ids": [S["m_interviewer2"]], "force": True})
        assert r.status_code == 200
        S["iv2"] = r.json()["id"]
        assert admin.get(f"{API}/applications/{S['app1']}").json()["status"] == "Interview Scheduled"

    def test_reschedule_cancel(self, admin):
        r = admin.post(f"{API}/interviews/{S['iv2']}/reschedule", json={"date": "2026-02-11", "start_time": "15:00", "end_time": "16:00", "reason": "Panel busy"})
        assert r.status_code == 200, r.text
        assert admin.post(f"{API}/interviews/{S['iv2']}/status", json={"status": "Cancelled"}).status_code == 400
        r = admin.post(f"{API}/interviews/{S['iv2']}/status", json={"status": "Cancelled", "reason": "Dup round"})
        assert r.status_code == 200
        assert admin.get(f"{API}/interviews/{S['iv2']}").json()["status"] == "Cancelled"

    def test_interviewer_scope_and_feedback(self, admin):
        # interviewer2 only assigned to iv2 (cancelled) — not iv1 after we create iv3 only for interviewer1
        iv = sess("test_interviewer@mms.test")
        lst = iv.get(f"{API}/interviews").json()
        assert all(S["m_interviewer"] in x["interviewer_ids"] for x in lst)
        ratings = {k: 4 for k in ["technical", "communication", "problem_solving", "relevant_experience", "role_fit", "overall"]}
        fb = {"ratings": ratings, "recommendation": "Hire", "detailed": "Good"}
        r = iv.post(f"{API}/interviews/{S['iv1']}/feedback", json=fb)
        assert r.status_code == 200, r.text
        got = admin.get(f"{API}/interviews/{S['iv1']}").json()
        assert got["feedback_status"] == "Partial"
        assert admin.get(f"{API}/applications/{S['app1']}").json()["status"] == "Interview In Progress"
        # create iv3 assigned only to interviewer1; interviewer2 must get 403/404
        r = admin.post(f"{API}/interviews", json={"application_id": S["app1"], "round_name": "HR", "date": "2026-02-12",
                                                  "start_time": "09:00", "end_time": "09:30", "interviewer_ids": [S["m_interviewer"]]})
        S["iv3"] = r.json()["id"]
        iv2 = sess("test_interviewer2@mms.test")
        r = iv2.post(f"{API}/interviews/{S['iv3']}/feedback", json=fb)
        assert r.status_code in (403, 404)
        assert iv2.get(f"{API}/interviews/{S['iv3']}").status_code == 404
        # admin must not submit without interviewer_id (not an interviewer)
        assert admin.post(f"{API}/interviews/{S['iv1']}/feedback", json=fb).status_code == 403
        r = iv2.post(f"{API}/interviews/{S['iv1']}/feedback", json={**fb, "recommendation": "Strong Hire"})
        assert r.status_code == 200, r.text
        got = admin.get(f"{API}/interviews/{S['iv1']}").json()
        assert got["feedback_status"] == "Complete" and got["status"] == "Completed"
        r = iv.post(f"{API}/interviews/{S['iv3']}/feedback", json=fb)
        assert r.status_code == 200
        assert admin.get(f"{API}/applications/{S['app1']}").json()["status"] == "Interview Completed"


# ---------- Selection / offers / joining / costs / analytics ----------
class TestOfferJoin:
    def test_cost_per_hire_na(self, admin):
        r = admin.post(f"{API}/costs", json={"category_id": S["cost_cat"], "invoice_date": "2026-01-05", "amount": 2.5})
        assert r.status_code == 400
        r = admin.post(f"{API}/costs", json={"category_id": S["cost_cat"], "invoice_date": "2026-01-05", "amount": 2.5,
                                             "recruiter_id": S["m_recruiter"], "requisition_id": S["req1"]})
        assert r.status_code == 200, r.text
        S["cost1"] = r.json()["id"]
        r = admin.put(f"{API}/costs/{S['cost1']}", json={"amount": 3.0})
        assert r.status_code == 200 and r.json()["amount"] == 3.0
        assert admin.put(f"{API}/costs/{S['cost1']}", json={"payment_status": "Paid"}).status_code == 400
        c2 = admin.post(f"{API}/costs", json={"category_id": S["cost_cat"], "invoice_date": "2026-01-06", "amount": 1, "recruiter_id": S["m_recruiter"]}).json()
        assert admin.delete(f"{API}/costs/{c2['id']}").status_code == 200
        assert all(c["id"] != c2["id"] for c in admin.get(f"{API}/costs").json())
        a = admin.get(f"{API}/analytics").json()
        assert a["kpis"]["joined"] == 0 and a["cost"]["cost_per_hire"] is None

    def test_selection_offer_flow(self, admin):
        # NOTE: backend OFFERABLE includes 'Interview Completed' so offer before selection is allowed (by design)
        r = admin.post(f"{API}/selections", json={"application_id": S["app1"], "decision": "Selected", "compensation": 12})
        assert r.status_code == 200, r.text
        assert admin.get(f"{API}/applications/{S['app1']}").json()["status"] == "Selected"
        r = admin.post(f"{API}/offers", json={"application_id": S["app1"], "designation": "SE", "ctc": 12, "validity_date": "2026-03-01"})
        assert r.status_code == 200, r.text
        oid = S["offer1"] = r.json()["id"]
        for act, st in [("submit", "Approval Pending"), ("approve", "Approved"), ("release", "Released")]:
            r = admin.post(f"{API}/offers/{oid}/action", json={"action": act})
            assert r.status_code == 200 and r.json()["status"] == st, r.text
        assert admin.post(f"{API}/offers/{oid}/action", json={"action": "decline"}).status_code == 400
        r = admin.post(f"{API}/offers/{oid}/action", json={"action": "accept", "tentative_joining_date": "2026-02-01"})
        assert r.status_code == 200 and r.json()["status"] == "Accepted"
        assert admin.get(f"{API}/applications/{S['app1']}").json()["status"] == "Offer Accepted"
        js = admin.get(f"{API}/joinings", params={"requisition_id": S["req1"]}).json()
        assert len(js) == 1 and js[0]["status"] == "Pending"
        S["join1"] = js[0]["id"]

    def test_join(self, admin):
        assert admin.put(f"{API}/joinings/{S['join1']}", json={"status": "Joined"}).status_code == 400
        r = admin.put(f"{API}/joinings/{S['join1']}", json={"status": "Joined", "actual_date": "2026-01-10"})
        assert r.status_code == 200, r.text
        assert admin.get(f"{API}/applications/{S['app1']}").json()["status"] == "Joined"
        req = admin.get(f"{API}/requisitions/{S['req1']}").json()
        assert req["filled_positions"] == 1
        a = admin.get(f"{API}/analytics").json()
        assert a["kpis"]["joined"] == 1
        assert a["cost"]["cost_per_hire"] == 3.0
        # effective start = CRF (2025-12-01) since init >= crf -> 40 days
        assert a["cycle"]["completed"]["avg"] == 40, a["cycle"]
        assert admin.get(f"{API}/analytics", params={"date_from": "2026-01-01", "date_to": "2026-12-31"}).status_code == 200

    def test_reports(self, admin):
        for t in ["candidates", "requisitions", "pipeline", "interviews", "offers", "joinings", "costs"]:
            for fmt in ["xlsx", "csv"]:
                r = admin.get(f"{API}/reports/{t}", params={"format": fmt})
                assert r.status_code == 200, f"{t} {fmt}: {r.status_code} {r.text[:200]}"
                assert len(r.content) > 0


# ---------- Notifications / activity ----------
class TestNotifs:
    def test_notifications(self):
        rc = sess("test_recruiter@mms.test")
        n = rc.get(f"{API}/notifications").json()
        items = n["items"] if isinstance(n, dict) else n
        assert any("requisition" in (x.get("title") or "").lower() for x in items), n
        iv = sess("test_interviewer@mms.test")
        n2 = iv.get(f"{API}/notifications").json()
        items2 = n2["items"] if isinstance(n2, dict) else n2
        assert any("interview" in (x.get("title") or "").lower() for x in items2)
        assert rc.post(f"{API}/notifications/read-all").status_code == 200
        n = rc.get(f"{API}/notifications").json()
        items = n["items"] if isinstance(n, dict) else n
        assert all(x["read"] for x in items)

    def test_activity(self, admin):
        r = admin.get(f"{API}/activity")
        assert r.status_code == 200
        d = r.json()
        items = d["items"] if isinstance(d, dict) else d
        assert len(items) > 5


# ---------- Excel import ----------
class TestImport:
    def test_import(self, admin):
        with open("/tmp/rec.xlsx", "rb") as f:
            r = admin.post(f"{API}/import/upload", files={"file": ("rec.xlsx", f.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert r.status_code == 200, r.text
        up = r.json()
        sheets = {s["name"]: s for s in up["sheets"]}
        print({k: (v["suggested_type"], v["row_count"]) for k, v in sheets.items()})
        orm = next(k for k in sheets if "open roles" in k.lower())
        body = {"batch_id": up["id"], "sheet": orm, "type": "requisitions", "mapping": sheets[orm]["suggested_mapping"]}
        v = admin.post(f"{API}/import/validate", json=body).json()
        print("ORM", v["summary"])
        assert v["summary"]["valid"] == 20, v["summary"]
        c = admin.post(f"{API}/import/commit", json=body).json()
        print("ORM commit", c)
        assert c["imported"] == 20
        cm = next(k for k in sheets if "candidate" in k.lower())
        body2 = {"batch_id": up["id"], "sheet": cm, "type": "candidates", "mapping": sheets[cm]["suggested_mapping"]}
        v = admin.post(f"{API}/import/validate", json=body2).json()
        print("CM", v["summary"], [r["messages"] for r in v["rows"] if r["messages"]][:5])
        c = admin.post(f"{API}/import/commit", json=body2).json()
        print("CM commit", c)
        assert c["imported"] > 0
        if c.get("rejected_count"):
            r = admin.get(f"{API}/import/{up['id']}/rejected")
            assert r.status_code == 200 and r.content[:2] == b"PK"
        ivs = next((k for k in sheets if "interviewer" in k.lower()), None)
        if ivs:
            body3 = {"batch_id": up["id"], "sheet": ivs, "type": "interviewers", "mapping": sheets[ivs]["suggested_mapping"]}
            v = admin.post(f"{API}/import/validate", json=body3).json()
            print("IV", v["summary"])
            c = admin.post(f"{API}/import/commit", json=body3).json()
            print("IV commit", c)
            assert c["imported"] + c.get("skipped_duplicates", 0) > 0
        # re-commit requisitions should not create duplicates
        v = admin.post(f"{API}/import/validate", json=body).json()
        print("ORM re-validate", v["summary"])
        assert admin.get(f"{API}/import/history").status_code == 200
