"""Recruitment workflow rules — one service shared by every endpoint that changes an application's stage.

* Transition matrix: which stage an application may move to from its current stage.
* Stage prerequisites: the records that must exist (screening, shortlisting, interviews + feedback,
  selection, offer, joining) before an application may be in a given stage.
* Readiness: completed / missing prerequisites for a requested destination, used by the guided wizard.
* Legacy records: applications that already existed (or were imported from Excel) before these controls
  keep the stages they had reached — those stages count as "recorded before workflow controls".
"""
from fastapi import HTTPException

from core import db, PIPELINE, TERMINAL, today

IDX = {s: i for i, s in enumerate(PIPELINE)}
ACTIVE_PIPELINE = PIPELINE[:-1]  # everything before Joined

# Terminal outcomes and the stages they can be reached from (reason always required)
TERMINAL_FROM = {
    "CV Rejected": ["New", "Screening", "Shortlisted", "On Hold"],
    "Interview Rejected": ["Interview Scheduled", "Interview In Progress", "Interview Completed"],
    "On Hold": ["New", "Screening", "Shortlisted", "Interview Scheduled", "Interview In Progress", "Interview Completed",
                "Selected", "Offer Approval Pending"],
    "Candidate Withdrawn": ACTIVE_PIPELINE + ["On Hold", "Offer Declined", "Offer Revoked"],
    "Offer Declined": ["Offer Released"],
    "Offer Revoked": ["Offer Approval Pending", "Offer Released", "Offer Accepted"],
    "No Show": ["Interview Scheduled", "Interview In Progress", "Offer Accepted"],
}
OVERRIDE_ROLES = {"super_admin"}  # authorized exceptions / waivers
SCREENING_DECISIONS = {"Screening": ["Cleared", "Rejected", "On Hold"], "Shortlisting": ["Shortlisted", "Rejected", "On Hold"]}


def static_matrix():
    """Matrix shown in Settings / used for menus. On Hold reactivation is refined per application (see allowed_targets)."""
    m = {}
    for s in PIPELINE:
        fwd = PIPELINE[IDX[s] + 1:] if s != "Joined" else []
        back = ["Interview Scheduled"] if s == "Interview Completed" else []  # next interview round
        m[s] = fwd + back + [t for t, src in TERMINAL_FROM.items() if s in src]
    m["On Hold"] = ACTIVE_PIPELINE + [t for t, src in TERMINAL_FROM.items() if "On Hold" in src]
    for t in ("Offer Declined", "Offer Revoked"):
        m[t] = ["Candidate Withdrawn"]  # a replacement offer is created from the Offers module (re-offer)
    for t in ("CV Rejected", "Interview Rejected", "Candidate Withdrawn", "No Show"):
        m[t] = []  # reopening needs an authorized exception
    return m


def held_from(app):
    for h in reversed(app.get("history") or []):
        if h.get("status") == "On Hold":
            return h.get("from")
    return None


async def allowed_targets(app):
    m = static_matrix()
    targets = list(m.get(app["status"], []))
    if app["status"] == "On Hold":
        prev = held_from(app)
        if prev in IDX:  # reactivate to the stage it was held from (or an earlier one)
            targets = [s for s in targets if s not in IDX or IDX[s] <= IDX[prev]]
    custom = ((await db.settings.find_one({"key": "general"}, {"transitions": 1})) or {}).get("transitions") or {}
    if app["status"] in custom:  # Settings may restrict the matrix further, never widen it
        targets = [s for s in targets if s in custom[app["status"]]]
    return targets


def legacy_index(app):
    v = app.get("legacy_stage_index")
    return v if isinstance(v, int) else -1


def reached_index(app):
    """Furthest pipeline stage an application has reached (used for the legacy marker)."""
    best = IDX.get(app.get("status"), -1)
    for h in app.get("history") or []:
        best = max(best, IDX.get(h.get("status"), -1))
    implied = {"CV Rejected": 1, "Interview Rejected": 4, "Offer Declined": 8, "Offer Revoked": 7, "No Show": 3}
    if best < 0:
        best = implied.get(app.get("status"), 0)
    return best


# ---------------- prerequisite checks ----------------
async def _reviews(app):
    out = {}
    async for r in db.stage_reviews.find({"application_id": app["id"], "active": True}, {"_id": 0}):
        out[r["stage"]] = r
    return out


async def interview_state(app, req):
    rounds_required = max(1, int((req or {}).get("interview_rounds_required") or 1))
    ivs = await db.interviews.find({"application_id": app["id"], "status": {"$ne": "Cancelled"}}, {"_id": 0}).sort("date", 1).to_list(200)
    fb = {}
    async for f in db.feedback.find({"application_id": app["id"]}, {"interview_id": 1, "interviewer_id": 1}):
        fb.setdefault(f["interview_id"], set()).add(f["interviewer_id"])
    complete, issues = [], []
    for iv in ivs:
        missing = set(iv.get("interviewer_ids") or []) - fb.get(iv["id"], set())
        if iv["status"] == "Completed":
            if missing and not iv.get("feedback_override"):
                issues.append(f"{iv['code']}: feedback missing from {len(missing)} interviewer(s)")
            else:
                complete.append(iv)
        elif iv["status"] in ("Scheduled", "Rescheduled"):
            issues.append(f"{iv['code']} ({iv.get('round_name')}) is not completed yet")
    final = complete[-1].get("outcome") if complete else None
    return {"rounds_required": rounds_required, "scheduled": len(ivs), "completed": len(complete), "issues": issues,
            "final_recommendation": final if final and final != "Pending" else None,
            "interview_ids": [i["id"] for i in ivs]}


def _step(key, stage, done, summary, missing=(), records=(), blocking=True, legacy=False):
    return {"key": key, "stage": stage, "done": bool(done), "legacy": legacy, "summary": summary,
            "missing": [m for m in missing if m], "record_ids": [r for r in records if r], "blocking": blocking}


async def evaluate(app, target):
    """Prerequisite steps for `app` to be in `target` (a pipeline stage). Returns ordered steps."""
    t = IDX.get(target)
    if t is None:
        return []
    legacy = legacy_index(app)
    req = await db.requisitions.find_one({"id": app["requisition_id"]}, {"_id": 0})
    reviews = await _reviews(app)
    steps = []

    if t >= IDX["Shortlisted"]:
        for stage, key, ok_decision, done_at in (("Screening", "screening", "Cleared", 2), ("Shortlisting", "shortlisting", "Shortlisted", 2)):
            r = reviews.get(stage)
            if legacy >= done_at and not r:
                steps.append(_step(key, stage, True, "Recorded before workflow controls", legacy=True))
            elif r and r.get("decision") == ok_decision:
                steps.append(_step(key, stage, True, f"{r['decision']} on {r['date']} by {r['owner']}", records=[r["id"]]))
            else:
                miss = ["date", "owner / reviewer", f"decision '{ok_decision}'"] if not r else [f"decision is '{r['decision']}', needs '{ok_decision}'"]
                steps.append(_step(key, stage, False, "Not recorded" if not r else f"{r['decision']} on {r['date']}", miss))

    if t >= IDX["Interview Scheduled"]:
        st = await interview_state(app, req)
        waiver = app.get("interview_waiver")
        if t <= IDX["Interview In Progress"]:
            ok = st["scheduled"] > 0
            steps.append(_step("interviews", "Interviews", ok or legacy >= 3,
                               f"{st['scheduled']} interview(s) scheduled" if ok else ("Recorded before workflow controls" if legacy >= 3 else "No interview scheduled"),
                               [] if ok or legacy >= 3 else ["schedule at least one interview round"], st["interview_ids"], legacy=not ok and legacy >= 3))
        elif waiver:
            steps.append(_step("interviews", "Interviews", True, f"Waived by {waiver['by']}: {waiver['reason']}"))
        elif legacy >= IDX["Interview Completed"] and st["completed"] == 0:
            steps.append(_step("interviews", "Interviews", True, "Recorded before workflow controls", legacy=True))
        else:
            miss = []
            if st["completed"] < st["rounds_required"]:
                miss.append(f"{st['rounds_required'] - st['completed']} more completed round(s) with all interviewer feedback "
                            f"({st['completed']}/{st['rounds_required']} done)")
            miss += st["issues"] if st["completed"] < st["rounds_required"] else []
            if st["completed"] and not st["final_recommendation"]:
                miss.append("final recommendation (outcome) on the last completed round")
            ok = not miss
            steps.append(_step("interviews", "Interviews", ok,
                               f"{st['completed']}/{st['rounds_required']} round(s) complete" + (f" · final: {st['final_recommendation']}" if st["final_recommendation"] else ""),
                               miss, st["interview_ids"]))

    if t >= IDX["Selected"]:
        sel = await db.selections.find_one({"application_id": app["id"], "active": {"$ne": False}, "decision": "Selected"}, {"_id": 0}, sort=[("created_at", -1)])
        if sel:
            steps.append(_step("selection", "Selection", True, f"Selected on {sel['selection_date']} by {sel['decision_maker']}"
                               + (f" at ₹{sel['compensation']} L" if sel.get("compensation") is not None else ""), records=[sel["id"]]))
        elif legacy >= IDX["Selected"]:
            steps.append(_step("selection", "Selection", True, "Recorded before workflow controls", legacy=True))
        else:
            steps.append(_step("selection", "Selection", False, "No selection decision", ["final decision", "decision maker", "selection date", "compensation"]))

    if t >= IDX["Offer Approval Pending"]:
        need = {7: ["Approval Pending", "Approved", "Released", "Accepted"], 8: ["Released", "Accepted"]}.get(t, ["Accepted"])
        offer = await db.offers.find_one({"application_id": app["id"], "status": {"$in": need}}, {"_id": 0}, sort=[("created_at", -1)])
        latest = await db.offers.find_one({"application_id": app["id"]}, {"_id": 0}, sort=[("created_at", -1)])
        label = {7: "submitted for approval", 8: "released"}.get(t, "accepted")
        if offer:
            bits = [f"{offer['code']} {offer['status']}", f"₹{offer.get('ctc')} L", offer.get("release_date") and f"released {offer['release_date']}",
                    offer.get("accepted_date") and f"accepted {offer['accepted_date']}"]
            steps.append(_step("offer", "Offer", True, " · ".join(b for b in bits if b), records=[offer["id"]]))
        else:
            miss = [f"an offer {label}"] if latest else ["offer record (designation, CTC, validity date)", "approval", f"offer {label}"]
            steps.append(_step("offer", "Offer", False, f"Latest offer {latest['code']} is {latest['status']}" if latest else "No offer", miss,
                               [latest["id"]] if latest else []))

    if t >= IDX["Joined"]:
        hc = app.get("hire_cost")
        steps.append(_step("cost", "Recruitment cost", bool(hc),
                           (f"CTC ₹{hc['ctc']} L + consulting ₹{hc['consulting_fee']} L + recruiter ₹{hc['recruiter_fee']} L = ₹{hc['total']} L "
                            f"(confirmed by {hc['confirmed_by']})") if hc else "Not confirmed",
                           [] if hc else ["annual CTC (> 0)", "consulting fees (0 allowed)", "recruiter fees (0 allowed)"]))
        j = await db.joinings.find_one({"application_id": app["id"], "status": {"$nin": ["Cancelled", "No Show"]}}, {"_id": 0})
        if j and j.get("status") == "Joined" and j.get("actual_date"):
            steps.append(_step("joining", "Joining", True, f"{j['code']} joined on {j['actual_date']}", records=[j["id"]]))
        else:
            steps.append(_step("joining", "Joining", False, f"{j['code']} is {j['status']}" if j else "No joining record",
                               ["actual date of joining", "document checklist"] if j else ["joining record (created when the offer is accepted)"],
                               [j["id"]] if j else []))
    return steps


async def readiness(app, target, user):
    allowed = await allowed_targets(app)
    steps = await evaluate(app, target) if target in IDX else []
    blocking = [s for s in steps if s["blocking"] and not s["done"]]
    return {"application_id": app["id"], "code": app.get("code"), "current": app["status"], "target": target,
            "transition_allowed": target in allowed, "allowed_targets": allowed, "steps": steps,
            "missing": [s["key"] for s in blocking], "can_move": target in allowed and not blocking,
            "can_override": user.get("role") in OVERRIDE_ROLES, "reason_required": target in TERMINAL}


async def assert_prerequisites(app, target, keys=None):
    """Raise 400 if blocking prerequisites for `target` are missing (optionally only the given step keys)."""
    steps = await evaluate(app, target)
    missing = [s for s in steps if s["blocking"] and not s["done"] and (keys is None or s["key"] in keys)]
    if missing:
        detail = "; ".join(f"{s['stage']}: {', '.join(s['missing']) or s['summary']}" for s in missing)
        raise HTTPException(400, {"message": f"Cannot move to {target} — complete the missing stages first", "missing": [s["key"] for s in missing], "detail": detail})


def is_override_user(user):
    return bool(user) and user.get("role") in OVERRIDE_ROLES


def not_future(d, label):
    if d and d > today():
        raise HTTPException(400, f"{label} cannot be in the future")
