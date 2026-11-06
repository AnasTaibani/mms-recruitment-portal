from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core import (db, get_user, require, can, now_iso, today, new_id, next_code, log_activity, notify, get_scope,
                  get_visible, masters_map, user_ids_for_person, admin_user_ids, set_app_status, recount_filled,
                  PAYMENT_STATUSES)

router = APIRouter(prefix="/api")
OPEN_OFFER = ["Draft", "Approval Pending", "Approved", "Released"]
OFFERABLE = ["Selected", "Offer Approval Pending", "Offer Declined", "Offer Revoked", "Interview Completed"]


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
    compensation: Optional[float] = None
    approval_status: Optional[str] = "Pending"
    remarks: Optional[str] = ""


@router.post("/selections")
async def record_selection(body: SelectionIn, user=Depends(require("selection.decide"))):
    app = await get_visible("applications", "app", body.application_id, await get_scope(user))
    if body.decision not in ("Selected", "Rejected", "On Hold"):
        raise HTTPException(400, "Decision must be Selected, Rejected or On Hold")
    if body.decision != "Selected" and not (body.remarks or "").strip():
        raise HTTPException(400, "Remarks are required when rejecting or holding")
    if app["status"] == "Joined":
        raise HTTPException(400, "Application already closed")
    doc = body.model_dump() | {"id": new_id(), "decided_by": user["name"], "decided_by_id": user["id"],
                               "decision_maker": body.decision_maker or user["name"],
                               "selection_date": body.selection_date or today(), "created_at": now_iso(),
                               "candidate_id": app["candidate_id"], "requisition_id": app["requisition_id"]}
    await db.selections.insert_one(doc)
    c, r = await labels(app)
    await log_activity(user, "selection", "application", app["id"], f"{c['name']} · {app['code']}",
                       f"{body.decision}" + (f" at ₹{body.compensation} L" if body.compensation else "") + (f" — {body.remarks}" if body.remarks else ""))
    target = {"Selected": "Selected", "Rejected": "Interview Rejected", "On Hold": "On Hold"}[body.decision]
    await set_app_status(app, target, user, reason=body.remarks, auto=True, note="Selection decision")
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
    if app["status"] not in OFFERABLE:
        raise HTTPException(400, f"Candidate must be Selected before an offer is created (current: {app['status']})")
    if await db.offers.find_one({"application_id": app["id"], "status": {"$in": OPEN_OFFER}}):
        raise HTTPException(409, "An open offer already exists for this application")
    if not body.designation or body.ctc is None or not body.validity_date:
        raise HTTPException(400, "Designation, offered CTC and validity date are required")
    ts = now_iso()
    doc = body.model_dump() | {"id": new_id(), "code": await next_code("OFF"), "candidate_id": app["candidate_id"],
                               "requisition_id": app["requisition_id"], "recruiter_id": app.get("recruiter_id"),
                               "status": "Draft", "approval_status": "Not Submitted", "created_by": user["id"],
                               "created_at": ts, "updated_at": ts,
                               "history": [{"at": ts, "by": user["name"], "action": "Created", "details": f"₹{body.ctc} L"}]}
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
    d = body.date or today()
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
        await set_app_status(app, APP_STATUS[body.action], user, reason=body.reason, auto=True, note=o["code"])
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
           "actual_date": None, "status": status, "checklist": await default_checklist(), "remarks": "",
           "created_at": ts, "updated_at": ts, "history": [{"at": ts, "by": user["name"] if user else "System", "action": status, "details": tentative or ""}]}
    await db.joinings.insert_one(doc)
    doc.pop("_id", None)
    await log_activity(user, "joining_create", "application", app["id"], doc["code"], f"Tentative {tentative or '—'}")
    return doc


async def mark_joined(app, user, actual_date):
    j = await db.joinings.find_one({"application_id": app["id"], "status": {"$nin": ["Cancelled", "No Show"]}}, {"_id": 0})
    if not j:
        j = await create_joining_doc(app, user)
    await db.joinings.update_one({"id": j["id"]}, {"$set": {"status": "Joined", "actual_date": actual_date, "updated_at": now_iso()},
                                                   "$push": {"history": {"at": now_iso(), "by": user["name"], "action": "Joined", "details": actual_date}}})
    await set_app_status(app, "Joined", user, auto=True, note=f"Joined on {actual_date}")
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
    if app["status"] not in ("Offer Accepted", "Offer Released"):
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
    if reason:
        data["status_reason"] = reason
    hist = {"at": now_iso(), "by": user["name"], "action": st or "Updated", "details": reason or ", ".join(k for k in data if k != "updated_at")}
    await db.joinings.update_one({"id": jid}, {"$set": {k: v for k, v in data.items() if not (st == "Joined" and k == "status")}, "$push": {"history": hist}})
    app = await db.applications.find_one({"id": j["application_id"]}, {"_id": 0})
    await log_activity(user, "joining_update", "application", app["id"], j["code"], f"{st or 'Updated'}" + (f" ({reason})" if reason else ""))
    if st == "Joined":
        await mark_joined(app, user, data["actual_date"])
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
    requisition_id: Optional[str] = None
    candidate_id: Optional[str] = None
    invoice_no: Optional[str] = None
    invoice_date: Optional[str] = None
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


def validate_cost(data, creating):
    if creating and (not data.get("category_id") or data.get("amount") is None or not data.get("invoice_date")):
        raise HTTPException(400, "Cost category, invoice date and amount are required")
    if creating and not (data.get("recruiter_id") or data.get("partner_id")):
        raise HTTPException(400, "Select the recruiter or recruitment partner this cost relates to")
    if data.get("payment_status") and data["payment_status"] not in PAYMENT_STATUSES:
        raise HTTPException(400, "Invalid payment status")
    if data.get("payment_status") == "Paid" and not data.get("payment_date"):
        raise HTTPException(400, "Payment date is required when marked Paid")


@router.post("/costs")
async def create_cost(body: CostIn, user=Depends(require("cost.manage"))):
    data = body.model_dump()
    data["payment_status"] = data.get("payment_status") or "Pending"
    validate_cost(data, True)
    doc = data | {"id": new_id(), "code": await next_code("CST"), "created_by": user["name"], "created_at": now_iso(), "updated_at": now_iso()}
    await db.costs.insert_one(doc)
    await log_activity(user, "cost_create", "cost", doc["id"], doc["code"], f"₹{doc['amount']} L · invoice {doc.get('invoice_no') or '—'}")
    doc.pop("_id", None)
    return doc


@router.put("/costs/{cid}")
async def update_cost(cid: str, body: CostIn, user=Depends(require("cost.manage"))):
    c = await db.costs.find_one({"id": cid}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Not found")
    data = body.model_dump(exclude_unset=True)
    validate_cost({**c, **data}, False)
    data["updated_at"] = now_iso()
    await db.costs.update_one({"id": cid}, {"$set": data})
    await log_activity(user, "cost_update", "cost", cid, c["code"], ", ".join(f"{k}: {c.get(k)} → {v}" for k, v in data.items() if k != "updated_at" and c.get(k) != v))
    return {**c, **data}


@router.delete("/costs/{cid}")
async def delete_cost(cid: str, user=Depends(require("cost.manage"))):
    c = await db.costs.find_one({"id": cid}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Not found")
    await db.costs.delete_one({"id": cid})
    await log_activity(user, "cost_delete", "cost", cid, c["code"], f"₹{c.get('amount')} L removed")
    return {"ok": True}
