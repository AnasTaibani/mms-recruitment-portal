from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core import (db, get_user, require, can, now_iso, today, new_id, next_code, log_activity, notify, get_scope,
                  get_visible, masters_map, user_ids_for_person, admin_user_ids, set_app_status, recount_filled,
                  PAYMENT_STATUSES)

router = APIRouter(prefix="/api")
OPEN_OFFER = ["Draft", "Approval Pending", "Approved", "Released"]
OFFERABLE = ["Selected", "Offer Approval Pending", "Offer Declined", "Offer Revoked"]  # re-offer after decline / revoke / expiry


async def labels(app):
    c = await db.candidates.find_one({"id": app["candidate_id"]}, {"_id": 0})
    r = await db.requisitions.find_one({"id": app["requisition_id"]}, {"_id": 0})
    return c, r


async def enrich(rows):
    mm = await masters_map()
    cands = {c["id"]: c async for c in db.candidates.find({"id": {"$in": list({x["candidate_id"] for x in rows})}}, {"_id": 0, "id": 1, "name": 1, "code": 1, "partner_id": 1, "source_id": 1})}
    reqs = {r["id"]: r async for r in db.requisitions.find({"id": {"$in": list({x["requisition_id"] for x in rows})}}, {"_id": 0, "id": 1, "title": 1, "code": 1, "department_id": 1, "recruiter_id": 1})}
    for x in rows:
        c, r = cands.get(x["candidate_id"], {}), reqs.get(x["requisition_id"], {})
        x.update({"candidate_name": c.get("name"), "candidate_code": c.get("code"), "requisition_title": r.get("title"),
                  "requisition_code": r.get("code"), "department": mm.get(r.get("department_id")),
                  "recruiter": mm.get(x.get("recruiter_id") or r.get("recruiter_id")),
                  "partner": mm.get(x.get("partner_id") or c.get("partner_id"))})
    return rows


# ---------- selection ----------
class SelectionIn(BaseModel):
    application_id: str
    decision: str
    decision_maker: Optional[str] = None
    selection_date: Optional[str] = None
    compensation: Optional[float] = Field(None, ge=0)
    approval_status: Optional[str] = None
    remarks: Optional[str] = ""
    override_reason: Optional[str] = None  # Super Admin: select without the required interviews (audited waiver)


SELECTION_APPROVAL = ["Pending", "Approved", "Rejected"]


@router.post("/selections")
async def record_selection(body: SelectionIn, user=Depends(require("selection.decide"))):
    from workflow import assert_prerequisites, is_override_user, not_future
    app = await get_visible("applications", "app", body.application_id, await get_scope(user))
    if body.decision not in ("Selected", "Rejected", "On Hold"):
        raise HTTPException(400, "Decision must be Selected, Rejected or On Hold")
    if not body.selection_date or not (body.decision_maker or "").strip():
        raise HTTPException(400, "Selection date and decision maker are required")
    not_future(body.selection_date, "Selection date")
    if body.decision != "Selected" and not (body.remarks or "").strip():
        raise HTTPException(400, "Remarks are required when rejecting or holding")
    if body.decision == "Selected" and (body.compensation is None or body.approval_status not in SELECTION_APPROVAL):
        raise HTTPException(400, "Compensation and approval status are required for a selection")
    if app["status"] == "Joined" or (app["closed"] and app["status"] != "On Hold"):
        raise HTTPException(400, f"Application is {app['status']} — a selection decision cannot be recorded")
    if await db.selections.find_one({"application_id": app["id"], "active": {"$ne": False}, "decision": "Selected"}):
        raise HTTPException(409, "An active selection already exists for this application")
    override = (body.override_reason or "").strip()
    if override and not is_override_user(user):
        raise HTTPException(403, "Only a Super Admin can record a selection without the required interviews")
    if not override:
        await assert_prerequisites(app, "Selected", keys={"screening", "shortlisting", "interviews"})
    ts = now_iso()
    doc = body.model_dump() | {"id": new_id(), "decided_by": user["name"], "decided_by_id": user["id"], "decision_maker": body.decision_maker.strip(),
                               "created_at": ts, "active": True, "candidate_id": app["candidate_id"], "requisition_id": app["requisition_id"],
                               "override": bool(override)}
    if override:  # the exception is stored on the application too, so later stages see the waived interviews
        await db.applications.update_one({"id": app["id"]}, {"$set": {"interview_waiver": {"reason": override, "by": user["name"], "by_id": user["id"], "at": ts}}})
        app["interview_waiver"] = {"reason": override, "by": user["name"]}
    await db.selections.update_many({"application_id": app["id"], "active": {"$ne": False}}, {"$set": {"active": False, "superseded_at": ts}})
    await db.selections.insert_one(doc)
    c, r = await labels(app)
    await log_activity(user, "selection", "application", app["id"], f"{c['name']} · {app['code']}",
                       f"{body.decision}" + (f" at ₹{body.compensation} L" if body.compensation else "") + (f" — {body.remarks}" if body.remarks else "")
                       + (f" [EXCEPTION: interviews waived — {override}]" if override else ""))
    target = {"Selected": "Selected", "Rejected": "Interview Rejected", "On Hold": "On Hold"}[body.decision]
    await set_app_status(app, target, user, reason=body.remarks, auto=True, note="Selection decision", records=[doc["id"]])
    doc.pop("_id", None)
    return doc


@router.get("/selections")
async def list_selections(application_id: Optional[str] = None, user=Depends(require("app.view"))):
    scope = await get_scope(user)
    q = scope.q("offer")
    if application_id:
        q = {**q, "application_id": application_id} if q else {"application_id": application_id}
    return await db.selections.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)


# ---------- offers ----------
class OfferIn(BaseModel):
    application_id: Optional[str] = None
    designation: Optional[str] = None
    ctc: Optional[float] = Field(None, ge=0)
    fixed: Optional[float] = None
    variable: Optional[float] = None
    other: Optional[float] = None
    release_date: Optional[str] = None
    validity_date: Optional[str] = None
    remarks: Optional[str] = None


async def list_offers(user, f):
    q = dict((await get_scope(user)).q("offer"))
    for k in ("status", "requisition_id", "candidate_id", "approval_status"):
        if f.get(k):
            q[k] = f[k]
    return await enrich(await db.offers.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000))


@router.get("/offers")
async def get_offers(request: Request, user=Depends(require("offer.view"))):
    return await list_offers(user, dict(request.query_params))


@router.post("/offers")
async def create_offer(body: OfferIn, user=Depends(require("offer.manage"))):
    app = await get_visible("applications", "app", body.application_id or "", await get_scope(user))
    from workflow import assert_prerequisites, legacy_index, IDX
    if await db.offers.find_one({"application_id": app["id"], "status": {"$in": OPEN_OFFER + ["Accepted"]}}):
        raise HTTPException(409, "An active offer already exists for this application")
    previous = await db.offers.find_one({"application_id": app["id"]}, {"_id": 0}, sort=[("created_at", -1)])
    legacy_without_offer = not previous and legacy_index(app) >= IDX["Offer Approval Pending"] and app["status"] in IDX
    if app["status"] not in OFFERABLE and not legacy_without_offer:
        raise HTTPException(400, f"Candidate must be Selected before an offer is created (current: {app['status']})")
    await assert_prerequisites(app, "Selected", keys={"selection"})
    if not body.designation or body.ctc is None or not body.validity_date:
        raise HTTPException(400, "Designation, offered CTC and validity date are required")
    ts = now_iso()
    doc = body.model_dump() | {"id": new_id(), "code": await next_code("OFF"), "candidate_id": app["candidate_id"],
                               "requisition_id": app["requisition_id"], "recruiter_id": app.get("recruiter_id"),
                               "status": "Draft", "approval_status": "Not Submitted", "created_by": user["id"],
                               "created_at": ts, "updated_at": ts, "replaces": previous["id"] if previous else None,
                               "history": [{"at": ts, "by": user["name"], "action": "Created" if not previous else f"Re-offer (replaces {previous['code']}, {previous['status']})",
                                            "details": f"₹{body.ctc} L"}]}
    await db.offers.insert_one(doc)
    c, r = await labels(app)
    await log_activity(user, "offer_create", "application", app["id"], f"{c['name']} · {doc['code']}", f"{body.designation} at ₹{body.ctc} L")
    doc.pop("_id", None)
    return doc


@router.put("/offers/{oid}")
async def update_offer(oid: str, body: OfferIn, user=Depends(require("offer.manage"))):
    o = await get_visible("offers", "offer", oid, await get_scope(user))
    if o["status"] not in ("Draft", "Approval Pending"):
        raise HTTPException(400, "Only draft or pending offers can be edited")
    data = body.model_dump(exclude_unset=True)
    data.pop("application_id", None)
    data["updated_at"] = now_iso()
    await db.offers.update_one({"id": oid}, {"$set": data, "$push": {"history": {"at": now_iso(), "by": user["name"], "action": "Edited", "details": ", ".join(data)}}})
    await log_activity(user, "offer_update", "application", o["application_id"], o["code"], ", ".join(k for k in data if k != "updated_at"))
    return {**o, **data}


class OfferAction(BaseModel):
    action: str
    date: Optional[str] = None
    reason: Optional[str] = None
    tentative_joining_date: Optional[str] = None


ACTIONS = {"submit": (["Draft"], "Approval Pending", "offer.manage"),
           "approve": (["Approval Pending"], "Approved", "offer.approve"),
           "reject": (["Approval Pending"], "Draft", "offer.approve"),
           "release": (["Approved"], "Released", "offer.manage"),
           "accept": (["Released"], "Accepted", "offer.manage"),
           "decline": (["Released", "Approved"], "Declined", "offer.manage"),
           "revoke": (["Approved", "Released", "Accepted"], "Revoked", "offer.manage")}
APP_STATUS = {"submit": "Offer Approval Pending", "release": "Offer Released", "accept": "Offer Accepted",
              "decline": "Offer Declined", "revoke": "Offer Revoked"}


@router.post("/offers/{oid}/action")
async def offer_action(oid: str, body: OfferAction, user=Depends(get_user)):
    if body.action not in ACTIONS:
        raise HTTPException(400, "Unknown action")
    allowed_from, new_status, perm = ACTIONS[body.action]
    if not can(user, perm):
        raise HTTPException(403, "You are not permitted to perform this action")
    o = await get_visible("offers", "offer", oid, await get_scope(user))
    if o["status"] not in allowed_from:
        raise HTTPException(400, f"Cannot {body.action} an offer that is {o['status']}")
    if body.action in ("reject", "decline", "revoke") and not (body.reason or "").strip():
        raise HTTPException(400, "A reason is required")
    app0 = await db.applications.find_one({"id": o["application_id"]}, {"_id": 0, "status": 1, "closed": 1})
    if app0 and (app0["status"] == "Joined" or (app0.get("closed") and app0["status"] not in ("Offer Declined", "Offer Revoked"))):
        raise HTTPException(400, f"The application is {app0['status']} — offer actions are closed")
    from workflow import not_future
    d = body.date or today()
    not_future(d, "Date")
    if body.action == "accept" and o.get("release_date") and d < o["release_date"]:
        raise HTTPException(400, "Acceptance date cannot be before the release date")
    upd = {"status": new_status, "updated_at": now_iso()}
    if body.action == "submit":
        upd["approval_status"] = "Pending"
    elif body.action == "approve":
        upd |= {"approval_status": "Approved", "approved_by": user["name"], "approved_at": now_iso()}
    elif body.action == "reject":
        upd |= {"approval_status": "Rejected", "rejection_reason": body.reason}
    elif body.action == "release":
        upd["release_date"] = d
    elif body.action == "accept":
        upd["accepted_date"] = d
    elif body.action == "decline":
        upd |= {"declined_date": d, "decline_reason": body.reason}
    elif body.action == "revoke":
        upd |= {"revoked_date": d, "revoke_reason": body.reason}
    await db.offers.update_one({"id": oid}, {"$set": upd, "$push": {"history": {"at": now_iso(), "by": user["name"], "action": new_status if body.action != "reject" else "Approval Rejected", "details": body.reason or d}}})
    app = await db.applications.find_one({"id": o["application_id"]}, {"_id": 0})
    c, r = await labels(app)
    await log_activity(user, f"offer_{body.action}", "application", app["id"], f"{c['name']} · {o['code']}", f"{o['status']} → {new_status}" + (f" ({body.reason})" if body.reason else ""))
    if body.action in APP_STATUS:
        await set_app_status(app, APP_STATUS[body.action], user, reason=body.reason, auto=True, note=o["code"], records=[oid])
    elif body.action == "reject" and app["status"] == "Offer Approval Pending":  # back to Selected until a revised offer is submitted
        await set_app_status(app, "Selected", user, reason=body.reason, auto=True, note=f"{o['code']} approval rejected", records=[oid])
    if body.action == "submit":
        await notify(await admin_user_ids(), "offer", "Offer awaiting approval", f"{o['code']} · {c['name']} · ₹{o['ctc']} L", "/offers")
    if body.action in ("approve", "reject"):
        await notify(await user_ids_for_person(o.get("recruiter_id")), "offer", f"Offer {'approved' if body.action == 'approve' else 'rejected'}", f"{o['code']} · {c['name']}", "/offers")
    if body.action == "accept" and not await db.joinings.find_one({"application_id": app["id"], "status": {"$nin": ["Cancelled", "No Show"]}}):
        await create_joining_doc(app, user, body.tentative_joining_date)
    if body.action == "revoke":
        await db.joinings.update_many({"application_id": app["id"], "status": {"$in": ["Pending", "Joining Confirmed", "Joining Deferred"]}},
                                      {"$set": {"status": "Cancelled", "updated_at": now_iso()}})
    return await db.offers.find_one({"id": oid}, {"_id": 0})


# ---------- joining ----------
async def default_checklist():
    return [{"item": m["name"], "received": False} async for m in db.masters.find({"type": "document", "active": True}).sort("name", 1)]


async def create_joining_doc(app, user, tentative=None, status="Pending"):
    c = await db.candidates.find_one({"id": app["candidate_id"]}, {"partner_id": 1})
    ts = now_iso()
    doc = {"id": new_id(), "code": await next_code("JN"), "application_id": app["id"], "candidate_id": app["candidate_id"],
           "requisition_id": app["requisition_id"], "recruiter_id": app.get("recruiter_id"),
           "partner_id": (c or {}).get("partner_id"), "tentative_date": tentative, "confirmed_date": None,
           "actual_date": None, "status": status, "checklist": (cl := await default_checklist()), "checklist_status": checklist_status(cl), "remarks": "",
           "created_at": ts, "updated_at": ts, "history": [{"at": ts, "by": user["name"] if user else "System", "action": status, "details": tentative or ""}]}
    await db.joinings.insert_one(doc)
    doc.pop("_id", None)
    await log_activity(user, "joining_create", "application", app["id"], doc["code"], f"Tentative {tentative or '—'}")
    return doc


def checklist_status(items):
    items = items or []
    got = sum(1 for i in items if i.get("received"))
    return "Not applicable" if not items else "Complete" if got == len(items) else "Partial" if got else "Pending"


async def mark_joined(app, user, actual_date):
    """Joined needs an accepted offer and an existing joining record — it never creates them."""
    from workflow import not_future
    if not actual_date:
        raise HTTPException(400, "Actual date of joining is required")
    fresh = await db.applications.find_one({"id": app["id"]}, {"_id": 0, "hire_cost": 1})
    if not (fresh or {}).get("hire_cost"):
        raise HTTPException(400, "Confirm the recruitment cost (annual CTC, consulting fees and recruiter fees) before marking the candidate Joined")
    not_future(actual_date, "Actual date of joining")
    offer = await db.offers.find_one({"application_id": app["id"], "status": "Accepted"}, {"_id": 0})
    if not offer:
        from workflow import legacy_index, IDX
        if legacy_index(app) < IDX["Offer Accepted"]:
            raise HTTPException(400, "An accepted offer is required before the candidate can be marked Joined")
    elif offer.get("accepted_date") and actual_date < offer["accepted_date"]:
        raise HTTPException(400, "Actual date of joining cannot be before the offer acceptance date")
    j = await db.joinings.find_one({"application_id": app["id"], "status": {"$nin": ["Cancelled", "No Show"]}}, {"_id": 0})
    if not j:
        raise HTTPException(400, "No joining record exists for this candidate — it is created when the offer is accepted")
    await db.joinings.update_one({"id": j["id"]}, {"$set": {"status": "Joined", "actual_date": actual_date, "updated_at": now_iso(),
                                                            "checklist_status": checklist_status(j.get("checklist"))},
                                                   "$push": {"history": {"at": now_iso(), "by": user["name"], "action": "Joined", "details": actual_date}}})
    await set_app_status(app, "Joined", user, auto=True, note=f"Joined on {actual_date}", records=[j["id"]] + ([offer["id"]] if offer else []))
    filled = await recount_filled(app["requisition_id"])
    req = await db.requisitions.find_one({"id": app["requisition_id"]}, {"_id": 0})
    await log_activity(user, "joined", "requisition", req["id"], f"{req['code']} {req['title']}", f"Filled {filled}/{req.get('positions')}")
    if filled >= (req.get("positions") or 0):
        await notify(await admin_user_ids(), "joining", "All positions filled", f"{req['code']} · {req['title']} can now be closed", f"/requisitions/{req['id']}")


async def list_joinings(user, f):
    q = dict((await get_scope(user)).q("offer"))
    for k in ("status", "requisition_id", "candidate_id"):
        if f.get(k):
            q[k] = f[k]
    return await enrich(await db.joinings.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000))


@router.get("/joinings")
async def get_joinings(request: Request, user=Depends(require("joining.view"))):
    return await list_joinings(user, dict(request.query_params))


class JoiningIn(BaseModel):
    application_id: Optional[str] = None
    tentative_date: Optional[str] = None
    confirmed_date: Optional[str] = None
    actual_date: Optional[str] = None
    status: Optional[str] = None
    checklist: Optional[List[dict]] = None
    remarks: Optional[str] = None
    reason: Optional[str] = None


@router.post("/joinings")
async def add_joining(body: JoiningIn, user=Depends(require("joining.manage"))):
    app = await get_visible("applications", "app", body.application_id or "", await get_scope(user))
    if app["status"] != "Offer Accepted" or not await db.offers.find_one({"application_id": app["id"], "status": "Accepted"}):
        raise HTTPException(400, "Joining can only be tracked after the offer is accepted")
    if await db.joinings.find_one({"application_id": app["id"], "status": {"$nin": ["Cancelled", "No Show"]}}):
        raise HTTPException(409, "A joining record already exists")
    return await create_joining_doc(app, user, body.tentative_date)


@router.put("/joinings/{jid}")
async def update_joining(jid: str, body: JoiningIn, user=Depends(require("joining.manage"))):
    j = await get_visible("joinings", "offer", jid, await get_scope(user))
    data = body.model_dump(exclude_unset=True)
    reason = data.pop("reason", None)
    data.pop("application_id", None)
    st = data.get("status")
    if j["status"] in ("Joined", "Cancelled", "No Show") and st and st != j["status"]:
        raise HTTPException(400, f"Joining record is {j['status']} and closed")
    if st == "Joined":
        if not data.get("actual_date"):
            raise HTTPException(400, "Actual date of joining is required")
    if st == "Joining Confirmed" and not (data.get("confirmed_date") or j.get("confirmed_date")):
        raise HTTPException(400, "Confirmed joining date is required")
    if st in ("Joining Deferred", "No Show", "Cancelled") and not (reason or "").strip():
        raise HTTPException(400, "A reason is required")
    if st == "Joining Deferred" and not data.get("tentative_date"):
        raise HTTPException(400, "Provide the new tentative joining date")
    data["updated_at"] = now_iso()
    if "checklist" in data:
        data["checklist_status"] = checklist_status(data["checklist"])
    if reason:
        data["status_reason"] = reason
    hist = {"at": now_iso(), "by": user["name"], "action": st or "Updated", "details": reason or ", ".join(k for k in data if k != "updated_at")}
    app = await db.applications.find_one({"id": j["application_id"]}, {"_id": 0})
    if st == "Joined":  # validate (accepted offer, dates) before anything is written
        await mark_joined(app, user, data["actual_date"])
    await db.joinings.update_one({"id": jid}, {"$set": {k: v for k, v in data.items() if not (st == "Joined" and k == "status")},
                                               **({} if st == "Joined" else {"$push": {"history": hist}})})
    await log_activity(user, "joining_update", "application", app["id"], j["code"], f"{st or 'Updated'}" + (f" ({reason})" if reason else ""))
    if st == "Joined":
        pass
    elif st == "No Show":
        await set_app_status(app, "No Show", user, reason=reason, auto=True, note=j["code"])
    elif st == "Cancelled":
        await set_app_status(app, "Candidate Withdrawn", user, reason=reason, auto=True, note=j["code"])
    elif st == "Joining Confirmed":
        await notify(await user_ids_for_person(app.get("recruiter_id")) + await admin_user_ids(), "joining", "Joining confirmed",
                     f"{j['code']} on {data.get('confirmed_date') or j.get('confirmed_date')}", "/joining")
    return (await enrich([await db.joinings.find_one({"id": jid}, {"_id": 0})]))[0]


# ---------- costs ----------
class CostIn(BaseModel):
    category_id: Optional[str] = None
    recruiter_id: Optional[str] = None
    partner_id: Optional[str] = None
    partner_name: Optional[str] = None  # free text; matched to (or added to) Master Data → Recruitment Partners
    requisition_id: Optional[str] = None
    candidate_id: Optional[str] = None
    invoice_no: Optional[str] = None
    invoice_date: Optional[str] = None
    ctc: Optional[float] = Field(None, ge=0)                    # candidate CTC in ₹ lakhs — only to work out a %-based fee; never counted as a cost
    fee_percent: Optional[float] = Field(None, ge=0, le=100)    # e.g. 8.33 for M2S, 7 for other partners
    amount: Optional[float] = Field(None, ge=0)
    payment_status: Optional[str] = None
    payment_date: Optional[str] = None
    remarks: Optional[str] = None


async def list_costs(user, f):
    q = {}
    for k in ("category_id", "recruiter_id", "partner_id", "requisition_id", "payment_status"):
        if f.get(k):
            q[k] = f[k]
    if f.get("date_from") or f.get("date_to"):
        q["invoice_date"] = {k: v for k, v in (("$gte", f.get("date_from")), ("$lte", f.get("date_to"))) if v}
    rows = await db.costs.find(q, {"_id": 0}).sort("invoice_date", -1).to_list(10000)
    mm = await masters_map()
    reqs = {r["id"]: r async for r in db.requisitions.find({}, {"_id": 0, "id": 1, "title": 1, "code": 1, "department_id": 1})}
    cands = {c["id"]: c["name"] async for c in db.candidates.find({"id": {"$in": [r.get("candidate_id") for r in rows if r.get("candidate_id")]}}, {"id": 1, "name": 1})}
    out = []
    for r in rows:
        req = reqs.get(r.get("requisition_id"), {})
        if f.get("department_id") and req.get("department_id") != f["department_id"]:
            continue
        if f.get("role") and f["role"].lower() not in (req.get("title") or "").lower():
            continue
        r.update({"category": mm.get(r.get("category_id")), "recruiter": mm.get(r.get("recruiter_id")),
                  "partner": mm.get(r.get("partner_id")), "requisition_title": req.get("title"),
                  "requisition_code": req.get("code"), "department": mm.get(req.get("department_id")),
                  "department_id": req.get("department_id"), "candidate_name": cands.get(r.get("candidate_id"))})
        out.append(r)
    return out


@router.get("/costs")
async def get_costs(request: Request, user=Depends(require("cost.view"))):
    return await list_costs(user, dict(request.query_params))


MAX_LAKHS = 1000  # ₹10 crore — anything above is almost certainly typed in rupees instead of lakhs


def apply_fee(data, current=None):
    """Amount = CTC × Fee % when both are given and no amount was typed (the form fills it in the same way)."""
    def check(k, label):
        v = {**(current or {}), **data}.get(k)
        if v is not None and v > MAX_LAKHS:
            raise HTTPException(400, f"{label} must be entered in ₹ lakhs — e.g. 35 for ₹35 lakh. {v:,.0f} looks like a rupee amount.")
    check("ctc", "Candidate CTC")
    m = {**(current or {}), **data}
    if data.get("amount") is None and m.get("ctc") is not None and m.get("fee_percent") is not None:
        data["amount"] = round(m["ctc"] * m["fee_percent"] / 100, 4)
    check("amount", "Fee amount")
    return data


async def link_cost(data, current=None):
    """Tie the cost to the candidate's application: infer the requisition when only one application fits."""
    m = {**(current or {}), **data}
    if m.get("candidate_id") and not m.get("requisition_id"):
        apps = await db.applications.find({"candidate_id": m["candidate_id"]}, {"_id": 0, "requisition_id": 1, "status": 1}).to_list(50)
        joined = [a for a in apps if a["status"] == "Joined"]
        pick = joined if len(joined) == 1 else apps if len(apps) == 1 else []
        if pick:
            data["requisition_id"] = pick[0]["requisition_id"]
    return data


async def sync_cost_status(candidate_id, requisition_id, user):
    """Cost reconciliation on the application follows its linked cost records (a manual "No Recruitment Cost" is replaced once a cost is added)."""
    if not candidate_id or not requisition_id:
        return
    app = await db.applications.find_one({"candidate_id": candidate_id, "requisition_id": requisition_id}, {"_id": 0})
    if not app:
        return
    costs = await db.costs.find({"candidate_id": candidate_id, "requisition_id": requisition_id}, {"_id": 0, "amount": 1}).to_list(100)
    if not costs:
        status = None if app.get("cost_status") in ("Cost Recorded", "Invoice Pending") and not app.get("cost_status_manual") else app.get("cost_status")
    else:
        status = "Cost Recorded" if all(c.get("amount") is not None for c in costs) else "Invoice Pending"
    if status != app.get("cost_status"):
        await db.applications.update_one({"id": app["id"]}, {"$set": {"cost_status": status, "cost_status_by": user["name"], "cost_status_at": now_iso(), "cost_status_manual": False}})
        await log_activity(user, "cost_status", "application", app["id"], app["code"], f"Cost reconciliation: {app.get('cost_status') or '—'} → {status or '—'} (from cost records)")


def validate_cost(data, creating):
    if creating and not data.get("category_id"):
        raise HTTPException(400, "Cost category is required")
    if data.get("payment_status") in ("Paid", "Partially Paid") and data.get("amount") is None:
        raise HTTPException(400, "Enter the amount before marking the cost as paid")
    if creating and not (data.get("recruiter_id") or data.get("partner_id")):
        raise HTTPException(400, "Select the recruiter or recruitment partner this cost relates to")
    if data.get("payment_status") and data["payment_status"] not in PAYMENT_STATUSES:
        raise HTTPException(400, "Invalid payment status")
    if data.get("payment_status") == "Paid" and not data.get("payment_date"):
        raise HTTPException(400, "Payment date is required when marked Paid")


@router.post("/costs")
async def create_cost(body: CostIn, user=Depends(require("cost.manage"))):
    from routes_recruit import resolve_named
    data = body.model_dump()
    if data.get("partner_name") is None:
        data.pop("partner_name", None)
    data = await resolve_named(data, user, "partner_name", "partner_id", "partner", "cost form")
    data = apply_fee(data)
    data = await link_cost(data)
    data["payment_status"] = data.get("payment_status") or "Pending"
    validate_cost(data, True)
    doc = data | {"id": new_id(), "code": await next_code("CST"), "created_by": user["name"], "created_at": now_iso(), "updated_at": now_iso()}
    await db.costs.insert_one(doc)
    await log_activity(user, "cost_create", "cost", doc["id"], doc["code"],
                       (f"₹{doc['amount']} L" if doc.get("amount") is not None else "amount not yet known") + f" · invoice {doc.get('invoice_no') or 'pending'}")
    await sync_cost_status(doc.get("candidate_id"), doc.get("requisition_id"), user)
    doc.pop("_id", None)
    return doc


@router.put("/costs/{cid}")
async def update_cost(cid: str, body: CostIn, user=Depends(require("cost.manage"))):
    c = await db.costs.find_one({"id": cid}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Not found")
    from routes_recruit import resolve_named
    data = await resolve_named(body.model_dump(exclude_unset=True), user, "partner_name", "partner_id", "partner", "cost form")
    data = apply_fee(data, c)
    data = await link_cost(data, c)
    validate_cost({**c, **data}, False)
    data["updated_at"] = now_iso()
    await db.costs.update_one({"id": cid}, {"$set": data})
    await sync_cost_status(c.get("candidate_id"), c.get("requisition_id"), user)
    m = {**c, **data}
    if (m.get("candidate_id"), m.get("requisition_id")) != (c.get("candidate_id"), c.get("requisition_id")):
        await sync_cost_status(m.get("candidate_id"), m.get("requisition_id"), user)
    await log_activity(user, "cost_update", "cost", cid, c["code"], ", ".join(f"{k}: {c.get(k)} → {v}" for k, v in data.items() if k != "updated_at" and c.get(k) != v))
    return {**c, **data}


@router.delete("/costs/{cid}")
async def delete_cost(cid: str, user=Depends(require("cost.manage"))):
    c = await db.costs.find_one({"id": cid}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Not found")
    await db.costs.delete_one({"id": cid})
    await log_activity(user, "cost_delete", "cost", cid, c["code"], f"₹{c.get('amount')} L removed")
    await sync_cost_status(c.get("candidate_id"), c.get("requisition_id"), user)
    return {"ok": True}


# ---------- Cost per hire: CTC + consulting fees + recruiter fees, confirmed per application before Joined ----------
HIRE_COST_FIELDS = (("ctc", "Candidate annual CTC"), ("consulting_fee", "Consulting fees"), ("recruiter_fee", "Recruiter fees"))
HIRE_COST_STAGES = ("Offer Accepted", "Joined")


class HireCostIn(BaseModel):
    ctc: Optional[float] = None             # annual CTC, ₹ lakhs
    consulting_fee: Optional[float] = None  # recruitment partner / consultancy fees, ₹ lakhs (0 allowed)
    recruiter_fee: Optional[float] = None   # recruiter fees, ₹ lakhs (0 allowed)
    currency: Optional[str] = "INR"
    ctc_basis: Optional[str] = "annual"
    reason: Optional[str] = None            # required when changing a confirmed cost
    total: Optional[float] = None           # ignored — the total is always calculated here


def hire_cost_total(hc):
    return round(hc["ctc"] + hc["consulting_fee"] + hc["recruiter_fee"], 4)


def validate_hire_cost(body):
    vals = {}
    for k, label in HIRE_COST_FIELDS:
        v = getattr(body, k)
        if v is None:  # blank is never read as zero
            raise HTTPException(400, f"{label} is required (enter 0 if there is none)" if k != "ctc" else f"{label} is required")
        if v < 0:
            raise HTTPException(400, f"{label} cannot be negative")
        if v > MAX_LAKHS:
            raise HTTPException(400, f"{label} must be entered in ₹ lakhs — e.g. 6 for ₹6,00,000. {v:,.0f} looks like a rupee amount.")
        vals[k] = round(float(v), 4)
    if vals["ctc"] <= 0:
        raise HTTPException(400, "Candidate annual CTC must be greater than zero")
    if (body.currency or "INR").upper() != "INR":
        raise HTTPException(400, "All amounts must be in INR (₹ lakhs)")
    if (body.ctc_basis or "annual").lower() != "annual":
        raise HTTPException(400, "CTC must be the annual CTC")
    return vals


async def hire_cost_suggestions(app):
    """Values already on record, offered as a starting point (never saved without the user confirming them)."""
    offer = await db.offers.find_one({"application_id": app["id"], "status": "Accepted"}, {"_id": 0, "ctc": 1, "code": 1})
    costs = await db.costs.find({"candidate_id": app["candidate_id"], "requisition_id": app["requisition_id"]}, {"_id": 0}).to_list(100)
    with_amt = [c for c in costs if c.get("amount") is not None]
    part = [c for c in with_amt if c.get("partner_id")]
    rec = [c for c in with_amt if not c.get("partner_id") and c.get("recruiter_id")]
    return {"ctc": offer.get("ctc") if offer else None, "ctc_source": f"accepted offer {offer['code']}" if offer else None,
            "consulting_fee": round(sum(c["amount"] for c in part), 4) if part else None,
            "recruiter_fee": round(sum(c["amount"] for c in rec) , 4) if rec else None,
            "cost_entries": len(costs)}


@router.get("/applications/{aid}/hire-cost")
async def get_hire_cost(aid: str, user=Depends(require("cost.view"))):
    app = await get_visible("applications", "app", aid, await get_scope(user))
    return {"application_id": aid, "hire_cost": app.get("hire_cost"), "history": app.get("hire_cost_history", []),
            "suggested": await hire_cost_suggestions(app), "can_edit": can(user, "cost.manage"), "status": app["status"]}


@router.put("/applications/{aid}/hire-cost")
async def confirm_hire_cost(aid: str, body: HireCostIn, user=Depends(require("cost.manage"))):
    """Confirm (or, with a reason, change) the cost of this hire. One record per application, kept on the application."""
    app = await get_visible("applications", "app", aid, await get_scope(user))
    if app["status"] not in HIRE_COST_STAGES:
        raise HTTPException(400, f"Recruitment cost is confirmed once the offer is accepted (current stage: {app['status']})")
    vals = validate_hire_cost(body)
    prev = app.get("hire_cost")
    reason = (body.reason or "").strip()
    if prev and not reason:
        raise HTTPException(400, "A reason is required to change confirmed cost details")
    ts = now_iso()
    hc = vals | {"total": hire_cost_total(vals), "currency": "INR", "unit": "lakhs", "ctc_basis": "annual",
                 "confirmed_by": (prev or {}).get("confirmed_by", user["name"]), "confirmed_by_id": (prev or {}).get("confirmed_by_id", user["id"]),
                 "confirmed_at": (prev or {}).get("confirmed_at", ts), "updated_by": user["name"], "updated_by_id": user["id"], "updated_at": ts,
                 "version": (prev or {}).get("version", 0) + 1, "candidate_id": app["candidate_id"], "requisition_id": app["requisition_id"]}
    if prev and all(prev.get(k) == hc[k] for k, _ in HIRE_COST_FIELDS):
        return {"hire_cost": prev, "history": app.get("hire_cost_history", []), "unchanged": True}
    entry = {"at": ts, "by": user["name"], "by_id": user["id"], "action": "Updated" if prev else "Confirmed", "reason": reason,
             "previous": {k: prev.get(k) for k in ("ctc", "consulting_fee", "recruiter_fee", "total")} if prev else None,
             "new": {k: hc[k] for k in ("ctc", "consulting_fee", "recruiter_fee", "total")}}
    guard = {"id": aid, "hire_cost.version": prev["version"]} if prev else {"id": aid, "hire_cost": {"$in": [None]}}
    res = await db.applications.update_one(guard, {"$set": {"hire_cost": hc, "updated_at": ts}, "$push": {"hire_cost_history": entry}})
    if not res.modified_count:
        raise HTTPException(409, "The cost details were changed by someone else — reload and try again")
    fmt = lambda d: f"CTC ₹{d['ctc']} L + consulting ₹{d['consulting_fee']} L + recruiter ₹{d['recruiter_fee']} L = ₹{d['total']} L"
    await log_activity(user, "hire_cost_update" if prev else "hire_cost_confirm", "application", aid, app.get("code", ""),
                       (f"{fmt(entry['previous'])} → {fmt(entry['new'])} ({reason})" if prev else fmt(entry["new"])))
    return {"hire_cost": hc, "history": app.get("hire_cost_history", []) + [entry]}
