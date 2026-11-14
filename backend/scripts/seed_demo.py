"""Load demo data for the HR walkthrough: 3 requisitions and 8 candidates at different stages.

Everything goes through the portal's normal API, so every workflow rule applies and every step is in the audit log
(recorded as the admin account you sign in with). Names are fictional; emails end in @demo-mms.example and phone
numbers start 90000, so they can't reach a real person.

Uses the setup lists that already exist (department, recruiter, interviewer, source, partner, cost category).
It creates no setup-list entries, users or settings. Remove it later with scripts/reset_for_rollout.py.

Usage (no extra packages needed):
    python scripts/seed_demo.py --api https://<your-backend>.onrender.com              # check only, creates nothing
    python scripts/seed_demo.py --api https://<your-backend>.onrender.com --execute
Admin email/password come from backend/.env (ADMIN_EMAIL / ADMIN_PASSWORD) or are asked for.
"""
import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

DOMAIN = "@demo-mms.example"
TODAY = date.today()
D = lambda n: (TODAY - timedelta(days=n)).isoformat()  # n days ago (negative = future)
RATINGS = {k: 4 for k in ["technical", "communication", "problem_solving", "relevant_experience", "role_fit", "overall"]}

REQS = {  # key: (title, positions, interview rounds, CRF days ago, budget min/max ₹ L, experience)
    "ba": ("Business Analyst", 2, 2, 40, 8, 14, "3-6 years"),
    "java": ("Java Developer", 3, 1, 35, 10, 18, "4-7 years"),
    "sa": ("Solution Architect", 1, 1, 60, 28, 40, "10+ years"),
}
CANDS = [  # name, requisition, target stage, company, designation, exp, current CTC, expected CTC
    ("Riya Mehta", "ba", "New", "Infosys", "Associate Business Analyst", 3.5, 7.5, 10),
    ("Karan Shah", "ba", "Screening", "Capgemini", "Business Analyst", 4, 9, 12),
    ("Neha Kulkarni", "ba", "Shortlisted", "Accenture", "Senior Business Analyst", 5.5, 11, 14),
    ("Rahul Verma", "ba", "CV Rejected", "Freelance", "Consultant", 2, 5, 9),
    ("Arjun Rao", "java", "Interview Scheduled", "TCS", "Java Developer", 5, 12, 16),
    ("Sneha Iyer", "java", "Interview Completed", "Wipro", "Senior Java Developer", 6, 13, 17),
    ("Vikram Desai", "sa", "Offer Released", "HCLTech", "Technical Architect", 12, 30, 38),
    ("Pooja Nair", "sa", "Joined", "Tech Mahindra", "Solution Architect", 11, 28, 34),
]


class Api:
    def __init__(self, base):
        self.base = base.rstrip("/")
        if not self.base.endswith("/api"):
            self.base += "/api"
        self.token = None

    def call(self, method, path, body=None, params=None):
        url = self.base + path
        if params:
            url += "?" + "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in params.items())
        req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {self.token}"} if self.token else {})})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read() or b"null")
        except urllib.error.URLError as e:
            if not isinstance(e, urllib.error.HTTPError):
                raise SystemExit(f"\nCan't reach the backend at {self.base} ({e.reason}). Check the --api address; on Render's free plan "
                                 f"open the site once and wait a minute for it to wake up. Nothing was created by this call.")
            raise SystemExit(f"\n{method} {path} failed ({e.code}): {e.read().decode()[:400]}\nStopped. Data created so far stays; "
                             f"fix the cause and remove it with reset_for_rollout.py, or finish the rest by hand.")
        except urllib.error.HTTPError as e:
            raise SystemExit(f"\n{method} {path} failed ({e.code}): {e.read().decode()[:400]}\nStopped. Data created so far stays; "
                             f"fix the cause and remove it with reset_for_rollout.py, or finish the rest by hand.")

    get = lambda s, p, **q: s.call("GET", p, params=q or None)
    post = lambda s, p, b: s.call("POST", p, b)
    put = lambda s, p, b: s.call("PUT", p, b)


def first(masters, kind, need_user=False, name=None, prefer=()):
    pool = [m for m in masters if m.get("type") == kind and m.get("active", True) and (m.get("user_id") or not need_user)]
    if name:
        hit = [m for m in pool if m["name"].strip().lower() == name.strip().lower()]
        if not hit:
            raise SystemExit(f"No active {kind} called '{name}'. Available: {', '.join(m['name'] for m in pool) or 'none'}. Nothing was created.")
        return hit[0]
    for word in prefer:
        hit = [m for m in pool if word in m["name"].lower()]
        if hit:
            return hit[0]
    return pool[0] if pool else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", required=True, help="backend URL, e.g. https://mms-backend.onrender.com")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--recruiter", help="recruiter to assign (exact name as in Master Data); default: the first one")
    ap.add_argument("--interviewer", help="interviewer for the interviews (must be linked to a user); default: the first one")
    a = ap.parse_args()

    env = {}
    p = Path(__file__).resolve().parent.parent / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    email = os.environ.get("ADMIN_EMAIL") or env.get("ADMIN_EMAIL") or input("Admin email: ")
    pw = os.environ.get("ADMIN_PASSWORD") or env.get("ADMIN_PASSWORD") or getpass.getpass("Admin password: ")

    api = Api(a.api)
    login = api.post("/auth/login", {"email": email.lower(), "password": pw})
    api.token = login["access_token"]
    me = login.get("user", {}).get("name") or "Super Admin"

    masters = api.get("/masters")
    dept, rec = first(masters, "department"), first(masters, "recruiter", name=a.recruiter)
    ivr = first(masters, "interviewer", need_user=True, name=a.interviewer)
    src, partner = first(masters, "source"), first(masters, "partner")
    cat = first(masters, "cost_category", prefer=("partner", "consult", "agency"))
    existing = [c for c in api.get("/candidates") if (c.get("email") or "").endswith(DOMAIN)]

    print(f"Backend      : {api.base}\nSigned in as : {me}")
    print(f"Department   : {dept['name'] if dept else '(none - requisitions without a department)'}")
    print(f"Recruiter    : {rec['name'] if rec else 'MISSING'}")
    print(f"Interviewer  : {ivr['name'] if ivr else 'MISSING'}")
    print(f"Source       : {src['name'] if src else '(none)'}   Partner: {partner['name'] if partner else '(none)'}   Cost category: {cat['name'] if cat else '(none)'}")
    if not rec or not ivr:
        raise SystemExit("\nNeeds at least one Recruiter and one Interviewer linked to a user (Users & Roles). Nothing was created.")
    if existing:
        raise SystemExit(f"\nDemo data is already loaded ({len(existing)} demo candidates found). Nothing was created.")
    print("\nWill create 3 requisitions and 8 candidates:")
    for n, r, stage, *_ in CANDS:
        print(f"  {n:<15} {REQS[r][0]:<20} -> {stage}")
    if not a.execute:
        print("\nCheck only - nothing created. Add --execute to load it.")
        return

    reqs = {}
    for k, (title, pos, rounds, crf, lo, hi, exp) in REQS.items():
        reqs[k] = api.post("/requisitions", {"title": title, "positions": pos, "interview_rounds_required": rounds, "crf_date": D(crf),
                                             "initiation_date": D(crf - 2), "status": "Open", "recruiter_id": rec["id"], "min_ctc": lo, "max_ctc": hi,
                                             "experience": exp, **({"department_id": dept["id"]} if dept else {})})["id"]
    out = []
    for i, (name, rk, stage, company, desig, exp, cur, expct) in enumerate(CANDS, 1):
        c = api.post("/candidates", {"name": name, "email": name.lower().replace(" ", ".") + DOMAIN, "phone": f"900000000{i}",
                                     "current_company": company, "current_designation": desig, "total_exp": exp, "relevant_exp": exp,
                                     "current_ctc": cur, "expected_ctc": expct, "notice_period": "30 days", "current_location": "Mumbai",
                                     "requisition_id": reqs[rk], "recruiter_id": rec["id"], **({"source_id": src["id"]} if src else {}), "force": True})
        aid = next(x["id"] for x in api.get("/applications", requisition_id=reqs[rk]) if x["candidate_id"] == c["id"])
        review = lambda st, dec, d: api.post(f"/applications/{aid}/stage-reviews", {"stage": st, "date": D(d), "owner": rec["name"], "decision": dec,
                                                                                     "remarks": "Demo data"})
        if stage == "CV Rejected":
            api.post(f"/applications/{aid}/status", {"status": "CV Rejected", "reason": "Experience below the role's requirement"})
        if stage in ("Screening", "Shortlisted", "Interview Scheduled", "Interview Completed", "Offer Released", "Joined"):
            review("Screening", "Cleared", 25)
        if stage in ("Shortlisted", "Interview Scheduled", "Interview Completed", "Offer Released", "Joined"):
            review("Shortlisting", "Shortlisted", 22)
        if stage == "Interview Scheduled":
            api.post("/interviews", {"application_id": aid, "round_name": "Technical Round", "date": D(-2), "start_time": "11:00", "end_time": "12:00",
                                     "mode": "Online", "interviewer_ids": [ivr["id"]], "force": True})
        if stage in ("Interview Completed", "Offer Released", "Joined"):
            iv = api.post("/interviews", {"application_id": aid, "round_name": "Technical Round", "date": D(18), "start_time": "11:00", "end_time": "12:00",
                                          "mode": "Online", "interviewer_ids": [ivr["id"]], "force": True})
            api.post(f"/interviews/{iv['id']}/feedback", {"interviewer_id": ivr["id"], "ratings": RATINGS, "recommendation": "Hire",
                                                          "detailed": "Strong fundamentals, clear communication. Recommended."})
            api.post(f"/interviews/{iv['id']}/status", {"outcome": "Selected"})
        if stage in ("Offer Released", "Joined"):
            api.post("/selections", {"application_id": aid, "decision": "Selected", "selection_date": D(15), "decision_maker": me,
                                     "compensation": expct, "remarks": "Demo data"})
            o = api.post("/offers", {"application_id": aid, "designation": desig if stage == "Joined" else "Solution Architect", "ctc": expct,
                                     "fixed": round(expct * 0.9, 2), "variable": round(expct * 0.1, 2), "validity_date": D(-20)})
            for act, d in (("submit", None), ("approve", None), ("release", D(12))) + ((("accept", D(10)),) if stage == "Joined" else ()):
                api.post(f"/offers/{o['id']}/action", {"action": act, **({"date": d} if d else {}),
                                                        **({"tentative_joining_date": D(4)} if act == "accept" else {})})
        if stage == "Joined":
            fee_pct = 8.33
            if partner and cat:
                api.post("/costs", {"category_id": cat["id"], "partner_id": partner["id"], "requisition_id": reqs[rk], "candidate_id": c["id"],
                                    "invoice_no": "DEMO-INV-001", "invoice_date": D(3), "ctc": expct, "fee_percent": fee_pct, "remarks": "Demo data"})
            fee = round(expct * fee_pct / 100, 4)
            api.put(f"/applications/{aid}/hire-cost", {"ctc": expct, "consulting_fee": fee, "consulting_fee_pct": fee_pct, "recruiter_fee": 0,
                                                       "currency": "INR", "ctc_basis": "annual"})
            j = next(x for x in api.get("/joinings", requisition_id=reqs[rk]) if x["application_id"] == aid)
            api.put(f"/joinings/{j['id']}", {"status": "Joined", "actual_date": D(4)})
        got = api.get(f"/applications/{aid}")
        out.append((name, REQS[rk][0], stage, got["status"], got.get("code")))

    print("\nLoaded:")
    for name, req, want, got, code in out:
        print(f"  {code}  {name:<15} {req:<20} {got}" + ("" if got == want else f"   (expected {want})"))
    bad = [o for o in out if o[2] != o[3]]
    print("\nAll 8 candidates are at the planned stage." if not bad else f"\n{len(bad)} candidate(s) ended at a different stage - check them before the demo.")


if __name__ == "__main__":
    main()
