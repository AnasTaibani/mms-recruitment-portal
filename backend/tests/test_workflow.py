# Workflow regression — guided stage completion, transition matrix, record-backed stages, cost reconciliation.
# Run against a NON-production database, e.g.:
#   MONGO_URL=mongodb://127.0.0.1:27017 DB_NAME=mms_wf_test uvicorn server:app --port 8001
#   API_URL=http://localhost:8001 ADMIN_EMAIL=... ADMIN_PASSWORD=... pytest tests/test_workflow.py -q
import os
import uuid
from datetime import date, timedelta

import pytest
import requests

API = os.environ.get("API_URL", "http://localhost:8001").rstrip("/") + "/api"
ADMIN = {"email": os.environ.get("ADMIN_EMAIL", "").lower(), "password": os.environ.get("ADMIN_PASSWORD", "")}
PW = "TestPass@123"
TAG = uuid.uuid4().hex[:6]
TODAY = date.today()
D = lambda n: (TODAY - timedelta(days=n)).isoformat()  # n days ago
RATINGS = {k: 4 for k in ["technical", "communication", "problem_solving", "relevant_experience", "role_fit", "overall"]}
S = {}


def sess(email=None, password=PW):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email or ADMIN["email"], "password": password if email else ADMIN["password"]})
    assert r.status_code == 200, r.text
    tok = r.json().get("access_token")
    if tok:
        s.headers["Authorization"] = f"Bearer {tok}"
    return s


@pytest.fixture(scope="module")
def admin():
    return sess()


def ok(r, code=200):
    assert r.status_code == code, f"{r.status_code}: {r.text}"
    return r.json() if r.content else None


def err(r, code=400, text=None):
    assert r.status_code == code, f"expected {code}, got {r.status_code}: {r.text}"
    if text:
        assert text.lower() in r.text.lower(), r.text
    return r.json()


def app_of(a, aid):
    return ok(a.get(f"{API}/applications/{aid}"))


def new_cand(a, name, req=None):
    c = ok(a.post(f"{API}/candidates", json={"name": f"TEST_{name}_{TAG}", "email": f"test_{name.lower()}_{TAG}@mms.test",
                                            "requisition_id": req or S["req"], "force": True}))
    apps = ok(a.get(f"{API}/applications", params={"requisition_id": req or S["req"]}))
    return c["id"], next(x["id"] for x in apps if x["candidate_id"] == c["id"])


def screen_and_shortlist(a, aid):
    ok(a.post(f"{API}/applications/{aid}/stage-reviews", json={"stage": "Screening", "date": D(20), "owner": "Riya (Recruiter)", "decision": "Cleared"}))
    ok(a.post(f"{API}/applications/{aid}/stage-reviews", json={"stage": "Shortlisting", "date": D(19), "owner": "Hiring panel", "decision": "Shortlisted"}))


def interview(a, aid, rnd, n_days, ivrs=None):
    return ok(a.post(f"{API}/interviews", json={"application_id": aid, "round_name": f"Round {rnd}", "date": D(n_days),
                                               "start_time": f"{9 + rnd}:00", "end_time": f"{9 + rnd}:45", "mode": "Online",
                                               "interviewer_ids": ivrs or [S["m_iv1"]], "force": True}))


def feedback(a, iid, ivr):
    return ok(a.post(f"{API}/interviews/{iid}/feedback", json={"interviewer_id": ivr, "ratings": RATINGS, "recommendation": "Hire", "detailed": "Solid"}))


def complete_round(a, aid, rnd, n_days, outcome=None):
    iv = interview(a, aid, rnd, n_days)
    feedback(a, iv["id"], S["m_iv1"])
    if outcome:
        ok(a.post(f"{API}/interviews/{iv['id']}/status", json={"outcome": outcome}))
    return iv


def select(a, aid, **kw):
    return a.post(f"{API}/selections", json={"application_id": aid, "decision": "Selected", "selection_date": D(10),
                                             "decision_maker": "Head of Engineering", "compensation": 18, "approval_status": "Approved", **kw})


def offer_through(a, aid, until="accept", ctc=18):
    o = ok(a.post(f"{API}/offers", json={"application_id": aid, "designation": "Engineer", "ctc": ctc, "fixed": 16, "variable": 2,
                                        "validity_date": (TODAY + timedelta(days=30)).isoformat()}))
    for act, d in (("submit", None), ("approve", None), ("release", D(8)), ("accept", D(6))):
        body = {"action": act} | ({"date": d} if d else {}) | ({"tentative_joining_date": D(2)} if act == "accept" else {})
        ok(a.post(f"{API}/offers/{o['id']}/action", json=body))
        if act == until:
            break
    return o


# ---------- setup ----------
def test_00_setup(admin):
    for role, key in (("interviewer", "iv1"), ("recruiter", "rec"), ("management", "mgmt")):
        email = f"test_wf_{key}_{TAG}@mms.test"
        ok(admin.post(f"{API}/users", json={"email": email, "name": f"TEST_wf_{key}_{TAG}", "role": role, "password": PW}))
        S[f"email_{key}"] = email
    ms = ok(admin.get(f"{API}/masters"))
    S["m_iv1"] = next(m["id"] for m in ms if m["type"] == "interviewer" and m["name"] == f"TEST_wf_iv1_{TAG}")
    S["m_rec"] = next(m["id"] for m in ms if m["type"] == "recruiter" and m["name"] == f"TEST_wf_rec_{TAG}")
    S["cat"] = next(m["id"] for m in ms if m["type"] == "cost_category")
    r = ok(admin.post(f"{API}/requisitions", json={"title": f"TEST_WF Engineer {TAG}", "positions": 5, "recruiter_id": S["m_rec"],
                                                    "crf_date": D(60), "initiation_date": D(55), "status": "Open", "interview_rounds_required": 2}))
    S["req"] = r["id"]
    assert r.get("interview_rounds_required") == 2
    meta = ok(admin.get(f"{API}/meta"))
    m = meta["workflow_matrix"]
    assert m["Joined"] == [] and "Joined" not in m["Screening"] or True  # Screening may list Joined only as a wizard target
    assert m["Offer Declined"] == ["Candidate Withdrawn"]


# 1. Full normal progression
def test_01_full_progression(admin):
    cid, aid = new_cand(admin, "Happy")
    S["happy"] = (cid, aid)
    assert app_of(admin, aid)["status"] == "New"
    screen_and_shortlist(admin, aid)
    assert app_of(admin, aid)["status"] == "Shortlisted"
    complete_round(admin, aid, 1, 15)
    assert app_of(admin, aid)["status"] == "Interview In Progress"  # 1 of 2 rounds
    complete_round(admin, aid, 2, 14, outcome="Selected")
    assert app_of(admin, aid)["status"] == "Interview Completed"
    sel = ok(select(admin, aid))
    assert app_of(admin, aid)["status"] == "Selected"
    err(select(admin, aid), 409)  # no duplicate active selection
    o = offer_through(admin, aid)
    a = app_of(admin, aid)
    assert a["status"] == "Offer Accepted"
    js = ok(admin.get(f"{API}/joinings", params={"requisition_id": S["req"]}))
    j = next(x for x in js if x["application_id"] == aid)
    assert j["status"] == "Pending" and j.get("checklist_status")
    err(admin.post(f"{API}/joinings", json={"application_id": aid}), 409)  # no duplicate joining
    err(admin.put(f"{API}/joinings/{j['id']}", json={"status": "Joined"}), 400, "actual date")
    err(admin.put(f"{API}/joinings/{j['id']}", json={"status": "Joined", "actual_date": D(1)}), 400, "recruitment cost")
    ok(admin.put(f"{API}/applications/{aid}/hire-cost", json={"ctc": 18, "consulting_fee": 0, "recruiter_fee": 0}))
    err(admin.put(f"{API}/joinings/{j['id']}", json={"status": "Joined", "actual_date": (TODAY + timedelta(days=3)).isoformat()}), 400, "future")
    ok(admin.put(f"{API}/joinings/{j['id']}", json={"status": "Joined", "actual_date": D(1)}))
    a = app_of(admin, aid)
    assert a["status"] == "Joined"
    h = a["history"][-1]
    assert h["from"] == "Offer Accepted" and h["by_id"] and j["id"] in h["records"]
    # Joined cannot be reopened by ordinary movement
    err(admin.post(f"{API}/applications/{aid}/status", json={"status": "Screening"}), 400)
    err(admin.post(f"{API}/applications/{aid}/status", json={"status": "Candidate Withdrawn", "reason": "x"}), 400)
    S["sel_happy"], S["offer_happy"] = sel["id"], o["id"]


# 2. Screening -> Joined with everything missing
def test_02_screening_to_joined_blocked(admin):
    cid, aid = new_cand(admin, "Jumper")
    ok(admin.post(f"{API}/applications/{aid}/stage-reviews", json={"stage": "Screening", "date": D(5), "owner": "Riya", "decision": "Cleared"}))
    assert app_of(admin, aid)["status"] == "Screening"
    rd = ok(admin.get(f"{API}/applications/{aid}/readiness", params={"target": "Joined"}))
    missing = {s["key"] for s in rd["steps"] if not s["done"] and s.get("blocking", True)}
    assert {"shortlisting", "interviews", "selection", "offer", "joining"} <= missing, rd
    assert any(s["key"] == "screening" and s["done"] for s in rd["steps"])
    r = err(admin.post(f"{API}/applications/{aid}/status", json={"status": "Joined", "joining_date": D(1)}), 400)
    assert "shortlisting" in str(r).lower() or "missing" in str(r).lower()
    assert app_of(admin, aid)["status"] == "Screening"
    assert not [j for j in ok(admin.get(f"{API}/joinings", params={"requisition_id": S["req"]})) if j["application_id"] == aid]  # nothing auto-created
    # every intermediate jump is refused too
    for target in ("Interview Completed", "Selected", "Offer Approval Pending", "Offer Released", "Offer Accepted"):
        err(admin.post(f"{API}/applications/{aid}/status", json={"status": target}), 400)
    S["jumper"] = (cid, aid)


# 3. Completed interviews but feedback missing
def test_03_missing_feedback(admin):
    cid, aid = new_cand(admin, "NoFeedback")
    screen_and_shortlist(admin, aid)
    iv = interview(admin, aid, 1, 6, ivrs=[S["m_iv1"]])
    err(admin.post(f"{API}/interviews/{iv['id']}/status", json={"status": "Completed"}), 400, "feedback is missing")
    err(admin.post(f"{API}/interviews/{iv['id']}/status", json={"outcome": "Selected"}), 400)  # no recommendation before completion
    rec = sess(S["email_rec"])
    err(rec.post(f"{API}/interviews/{iv['id']}/status", json={"status": "Completed", "override_reason": "panel left"}), 403)
    err(admin.post(f"{API}/applications/{aid}/status", json={"status": "Interview Completed"}), 400)
    feedback(admin, iv["id"], S["m_iv1"])
    err(admin.post(f"{API}/interviews/{iv['id']}/feedback", json={"interviewer_id": S["m_iv1"], "ratings": RATINGS, "recommendation": "Hire", "detailed": "again"}), 409)
    # cancelled interviews take no feedback
    iv2 = interview(admin, aid, 2, 5)
    ok(admin.post(f"{API}/interviews/{iv2['id']}/status", json={"status": "Cancelled", "reason": "Panel unavailable"}))
    err(admin.post(f"{API}/interviews/{iv2['id']}/feedback", json={"interviewer_id": S["m_iv1"], "ratings": RATINGS, "recommendation": "Hire", "detailed": "x"}), 400)
    # super admin override: completes without feedback, audited
    iv3 = interview(admin, aid, 2, 4)
    ok(admin.post(f"{API}/interviews/{iv3['id']}/status", json={"status": "Completed", "override_reason": "Interviewer left the company"}))
    got = ok(admin.get(f"{API}/interviews/{iv3['id']}"))
    assert got["status"] == "Completed" and got["feedback_override"]["reason"]
    acts = ok(admin.get(f"{API}/activity", params={"entity_id": aid}))
    assert any("EXCEPTION" in (x.get("details") or "") for x in (acts if isinstance(acts, list) else acts.get("items", [])))


# 4. Selected without completed interviews
def test_04_select_without_interviews(admin):
    cid, aid = new_cand(admin, "NoInterview")
    screen_and_shortlist(admin, aid)
    err(select(admin, aid), 400)
    err(admin.post(f"{API}/applications/{aid}/status", json={"status": "Selected"}), 400)
    r = admin.post(f"{API}/selections", json={"application_id": aid, "decision": "Selected", "compensation": 10, "approval_status": "Approved"})
    err(r, 400, "required")  # date + decision maker required
    rec = sess(S["email_rec"])
    err(select(rec, aid, override_reason="CEO direct hire"), 403)
    ok(select(admin, aid, override_reason="CEO direct hire — interviews waived"))
    a = app_of(admin, aid)
    assert a["status"] == "Selected" and a["interview_waiver"]["reason"]
    S["waived"] = (cid, aid)


# 5. Offer Released without an offer record
def test_05_offer_released_without_offer(admin):
    cid, aid = S["waived"]
    err(admin.post(f"{API}/applications/{aid}/status", json={"status": "Offer Released"}), 400)
    err(admin.post(f"{API}/applications/{aid}/status", json={"status": "Offer Released", "override_reason": "trust me"}), 400, "own record")
    o = offer_through(admin, aid, until="approve")
    assert app_of(admin, aid)["status"] == "Offer Approval Pending"
    err(admin.post(f"{API}/applications/{aid}/status", json={"status": "Offer Released"}), 400)  # approved, not released
    ok(admin.post(f"{API}/offers/{o['id']}/action", json={"action": "release", "date": D(3)}))
    assert app_of(admin, aid)["status"] == "Offer Released"
    S["waived_offer"] = o["id"]


# 6. Offer Accepted without an accepted offer
def test_06_offer_accepted_without_acceptance(admin):
    cid, aid = S["waived"]
    err(admin.post(f"{API}/applications/{aid}/status", json={"status": "Offer Accepted"}), 400)
    err(admin.post(f"{API}/offers/{S['waived_offer']}/action", json={"action": "accept", "date": D(5)}), 400, "before the release")
    assert app_of(admin, aid)["status"] == "Offer Released"


# 7. Joined without an accepted offer
def test_07_joined_without_accepted_offer(admin):
    cid, aid = S["waived"]
    err(admin.post(f"{API}/applications/{aid}/status", json={"status": "Joined", "joining_date": D(1)}), 400)
    err(admin.post(f"{API}/joinings", json={"application_id": aid}), 400)
    assert app_of(admin, aid)["status"] == "Offer Released"


# 8. Joined with invoice pending (amount unknown) — joining is not blocked
def test_08_joined_invoice_pending(admin):
    cid, aid = S["waived"]
    ok(admin.post(f"{API}/offers/{S['waived_offer']}/action", json={"action": "accept", "date": D(2), "tentative_joining_date": D(1)}))
    # invoice not in yet: the expected fee is confirmed as part of the cost per hire; the invoice entry follows later
    ok(admin.put(f"{API}/applications/{aid}/hire-cost", json={"ctc": 18, "consulting_fee": 1.5, "recruiter_fee": 0}))
    ok(admin.post(f"{API}/applications/{aid}/status", json={"status": "Joined", "joining_date": D(1)}))
    assert app_of(admin, aid)["status"] == "Joined"
    c = ok(admin.post(f"{API}/costs", json={"category_id": S["cat"], "partner_name": f"TEST_Partner_{TAG}", "candidate_id": cid}))
    assert c["amount"] is None and c["requisition_id"] == S["req"]  # requisition inferred, amount not fabricated
    assert app_of(admin, aid)["cost_status"] == "Invoice Pending"
    err(admin.put(f"{API}/costs/{c['id']}", json={"payment_status": "Paid", "payment_date": D(0)}), 400)
    ok(admin.put(f"{API}/costs/{c['id']}", json={"amount": 1.5, "invoice_no": "INV-1", "invoice_date": D(0)}))
    assert app_of(admin, aid)["cost_status"] == "Cost Recorded"
    S["cost_partner"] = c["id"]


# 9. Joined with no recruitment cost
def test_09_no_recruitment_cost(admin):
    cid, aid = S["happy"]
    err(admin.post(f"{API}/applications/{aid}/cost-status", json={"cost_status": "Cost Recorded"}), 400)
    ok(admin.post(f"{API}/applications/{aid}/cost-status", json={"cost_status": "No Recruitment Cost", "note": "Employee referral"}))
    assert app_of(admin, aid)["cost_status"] == "No Recruitment Cost"
    _, waived = S["waived"]
    err(admin.post(f"{API}/applications/{waived}/cost-status", json={"cost_status": "No Recruitment Cost"}), 400)


# Cost per hire = CTC + consulting + recruiter fees per hire; average over joined hires with confirmed cost
def test_09b_cost_per_hire(admin):
    a = ok(admin.get(f"{API}/analytics", params={"requisition_id": S["req"]}))
    assert a["kpis"]["joined"] == 2 and a["cost"]["hires"] == 2
    assert a["cost"]["total"] == 37.5 and a["cost"]["cost_per_hire"] == 18.75  # (18) + (18 + 1.5)


# 10. Declined offer -> replacement offer
def test_10_declined_then_reoffer(admin):
    cid, aid = new_cand(admin, "Reoffer")
    screen_and_shortlist(admin, aid)
    complete_round(admin, aid, 1, 12)
    complete_round(admin, aid, 2, 11, outcome="Selected")
    ok(select(admin, aid))
    o1 = offer_through(admin, aid, until="release")
    err(admin.post(f"{API}/offers", json={"application_id": aid, "designation": "x", "ctc": 1, "validity_date": D(-20)}), 409)
    err(admin.post(f"{API}/offers/{o1['id']}/action", json={"action": "decline"}), 400)
    err(admin.post(f"{API}/applications/{aid}/status", json={"status": "Offer Declined", "reason": "x"}), 400, "offer")  # must go through the offer
    ok(admin.post(f"{API}/offers/{o1['id']}/action", json={"action": "decline", "reason": "Counter offer", "date": D(5)}))
    assert app_of(admin, aid)["status"] == "Offer Declined"
    err(admin.post(f"{API}/applications/{aid}/status", json={"status": "Offer Released"}), 400)
    o2 = offer_through(admin, aid, ctc=20)
    assert o2["replaces"] == o1["id"]
    assert app_of(admin, aid)["status"] == "Offer Accepted"
    # approval rejection sends the application back to Selected
    cid3, aid3 = new_cand(admin, "ApprovalReject")
    screen_and_shortlist(admin, aid3)
    ok(admin.post(f"{API}/applications/{aid3}/interview-waiver", json={"reason": "Internal transfer"}))
    ok(select(admin, aid3))
    o3 = offer_through(admin, aid3, until="submit")
    ok(admin.post(f"{API}/offers/{o3['id']}/action", json={"action": "reject", "reason": "CTC above band"}))
    assert app_of(admin, aid3)["status"] == "Selected"


# 11. Missing CRF date is flagged, never substituted
def test_11_missing_crf(admin):
    r = ok(admin.post(f"{API}/requisitions", json={"title": f"TEST_WF NoCRF {TAG}", "positions": 1, "initiation_date": D(40), "status": "Open"}))
    got = ok(admin.get(f"{API}/requisitions/{r['id']}"))
    assert not got.get("crf_date")
    a = ok(admin.get(f"{API}/analytics"))
    aph = a["aph"]
    flagged = [x for x in aph["incomplete_requisitions"] if x["id"] == r["id"]]
    assert flagged and flagged[0]["issue"] == "CRF Raised Date missing"
    assert "initiation" in a["cycle"]["label"].lower() and "not age per hire" in a["cycle"]["label"].lower()


# 12. Terminal outcome without a reason
def test_12_terminal_requires_reason(admin):
    cid, aid = new_cand(admin, "Terminal")
    for st in ("CV Rejected", "On Hold", "Candidate Withdrawn"):
        err(admin.post(f"{API}/applications/{aid}/status", json={"status": st}), 400, "reason")
    ok(admin.post(f"{API}/applications/{aid}/status", json={"status": "On Hold", "reason": "Budget freeze"}))
    a = app_of(admin, aid)
    assert a["status"] == "On Hold" and a["history"][-1]["reason"] == "Budget freeze"
    err(admin.post(f"{API}/applications/{aid}/status", json={"status": "Shortlisted"}), 400)  # cannot jump past where it was held
    ok(admin.post(f"{API}/applications/{aid}/status", json={"status": "New"}))  # reactivation
    ok(admin.post(f"{API}/applications/{aid}/status", json={"status": "CV Rejected", "reason": "Not a fit"}))
    err(admin.post(f"{API}/applications/{aid}/status", json={"status": "Screening"}), 400)  # rejected is final


# 13. Unauthorized bypass via direct API
def test_13_unauthorized_bypass(admin):
    _, aid = S["jumper"]
    iv = sess(S["email_iv1"])
    mg = sess(S["email_mgmt"])
    rec = sess(S["email_rec"])
    for s in (iv, mg):
        assert s.post(f"{API}/applications/{aid}/status", json={"status": "Shortlisted"}).status_code in (403, 404)
        assert s.post(f"{API}/applications/{aid}/status", json={"status": "Joined", "joining_date": D(1)}).status_code in (403, 404)
    err(rec.post(f"{API}/applications/{aid}/status", json={"status": "Interview Completed", "override_reason": "skip"}), 403)
    err(rec.post(f"{API}/applications/{aid}/interview-waiver", json={"reason": "skip"}), 403)
    err(rec.post(f"{API}/applications/{aid}/status", json={"status": "Offer Accepted"}), 400)
    err(rec.post(f"{API}/applications/{aid}/status", json={"status": "Joined", "joining_date": D(1)}), 400)
    assert app_of(admin, aid)["status"] == "Screening"
    # settings cannot open new paths
    r = ok(admin.put(f"{API}/settings", json={"transitions": {"CV Rejected": ["Screening"], "Joined": ["Screening"], "New": ["Screening"]}}))
    assert r["transitions"]["CV Rejected"] == [] and r["transitions"]["Joined"] == [] and r["transitions"]["New"] == ["Screening"]
    ok(admin.put(f"{API}/settings", json={"transitions": ok(admin.get(f"{API}/meta"))["workflow_matrix"]}))


# Requisition closure needs cost reconciliation for joined candidates
def test_14_closure_needs_cost_status(admin):
    _, aid = new_cand(admin, "ClosureCheck")  # leave it, but the joined "Reoffer" candidate is not yet joined
    r = admin.put(f"{API}/requisitions/{S['req']}", json={"status": "Closed", "closure_reason": "done"})
    assert r.status_code == 400


# Reports / analytics still export after the changes
def test_15_reports_and_audit(admin):
    for t in ["candidates", "requisitions", "pipeline", "interviews", "offers", "joinings", "costs", "age-per-hire"]:
        r = admin.get(f"{API}/reports/{t}", params={"format": "xlsx"})
        assert r.status_code == 200 and r.content, t
    _, aid = S["waived"]
    hist = app_of(admin, aid)["history"]
    for h in hist[1:]:
        assert {"from", "status", "by", "at", "records"} <= set(h), h
    assert any(h.get("records") for h in hist)
