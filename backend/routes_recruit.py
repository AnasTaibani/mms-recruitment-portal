import re
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core import (db, get_user, require, can, now_iso, today, new_id, next_code, log_activity, notify, get_scope,
                  get_visible, masters_map, user_ids_for_person, person_ids, set_app_status, get_settings,
                  days_between, effective_start, INACTIVE, HM_ALLOWED, PIPELINE)

router = APIRouter(prefix="/api")


def rx(s):
    return {"$regex": re.escape(s.strip()), "$options": "i"}


# ---------- requisitions ----------
class ReqIn(BaseModel):
    title: Optional[str] = None
    job_title_id: Optional[str] = None
    department_id: Optional[str] = None
    hiring_manager_id: Optional[str] = None
    recruiter_id: Optional[str] = None
    positions: Optional[int] = Field(None, ge=0)
    experience: Optional[str] = None
    min_ctc: Optional[float] = None
    max_ctc: Optional[float] = None
    location_id: Optional[str] = None
    skills: Optional[List[str]] = None
    qualifications: Optional[str] = None
    employment_type_id: Optional[str] = None
    crf_date: Optional[str] = None
    initiation_date: Optional[str] = None
    priority_id: Optional[str] = None
    status: Optional[str] = None
    remarks: Optional[str] = None
    closure_reason: Optional[str] = None


REQ_LABELS = {"title": "Job title", "department_id": "Department", "hiring_manager_id": "Hiring manager",
              "recruiter_id": "Recruiter", "positions": "Positions", "status": "Status", "min_ctc": "Min CTC",
              "max_ctc": "Max CTC", "priority_id": "Priority", "crf_date": "CRF date", "initiation_date": "Initiation date"}


async def enrich_reqs(reqs):
    mm = await masters_map()
    ids = [r["id"] for r in reqs]
    stats = {}
    async for a in db.applications.find({"requisition_id": {"$in": ids}}, {"requisition_id": 1, "status": 1}):
        s = stats.setdefault(a["requisition_id"], {"total": 0, "active": 0, "by_status": {}})
        s["total"] += 1
        s["active"] += a["status"] not in INACTIVE and a["status"] != "On Hold"
        s["by_status"][a["status"]] = s["by_status"].get(a["status"], 0) + 1
    for r in reqs:
        for k in ("department", "hiring_manager", "recruiter", "location", "priority", "employment_type"):
            r[k] = mm.get(r.get(f"{k}_id"))
        s = stats.get(r["id"], {"total": 0, "active": 0, "by_status": {}})
        r["candidates_count"], r["active_count"], r["by_status"] = s["total"], s["active"], s["by_status"]
        r["open_positions"] = max((r.get("positions") or 0) - (r.get("filled_positions") or 0), 0)
        start = effective_start(r)
        r["effective_start"] = start
        r["age_days"] = days_between(start, today()) if start and r.get("status") in ("Open", "On Hold") else None
        crf = r.get("crf_date")
        r["current_hiring_age"] = days_between(crf, today()) if crf and crf <= today() and r.get("status") in ("Open", "On Hold") else None
        r["aph_flag"] = None if crf else "CRF Raised Date missing — Age per Hire unavailable"
    return reqs


async def list_requisitions(user, f):
    scope = await get_scope(user)
    q = dict(scope.q("req"))
    for k in ("status", "department_id", "recruiter_id", "hiring_manager_id", "priority_id"):
        if f.get(k):
            q[k] = f[k]
    if f.get("q"):
        q["$or"] = [{"title": rx(f["q"])}, {"code": rx(f["q"])}, {"skills": rx(f["q"])}]
    if f.get("date_from") or f.get("date_to"):
        q["created_at"] = {k: v for k, v in (("$gte", f.get("date_from")), ("$lte", (f.get("date_to") or "") + "T23:59:59")) if v and v != "T23:59:59"}
    reqs = await db.requisitions.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)
    return await enrich_reqs(reqs)


@router.get("/requisitions")
async def get_requisitions(request: Request, user=Depends(require("req.view"))):
    return await list_requisitions(user, dict(request.query_params))


async def validate_req(data):
    if data.get("min_ctc") is not None and data.get("max_ctc") is not None and data["min_ctc"] > data["max_ctc"]:
        raise HTTPException(400, "Minimum CTC cannot exceed maximum CTC")
    if data.get("status") and data["status"] not in ("Draft", "Open", "On Hold", "Closed", "Cancelled"):
        raise HTTPException(400, "Invalid status")
    if data.get("job_title_id") and not data.get("title"):
        m = await db.masters.find_one({"id": data["job_title_id"]})
        data["title"] = m["name"] if m else None


@router.post("/requisitions")
async def create_requisition(body: ReqIn, user=Depends(require("req.manage"))):
    data = body.model_dump()
    await validate_req(data)
    if not (data.get("title") or "").strip() or not data.get("positions"):
        raise HTTPException(400, "Job title and number of positions are required")
    if data.get("status") in ("Closed", "Cancelled"):
        raise HTTPException(400, "New requisitions must be Draft, Open or On Hold")
    ts = now_iso()
    doc = data | {"id": new_id(), "code": await next_code("REQ"), "status": data.get("status") or "Open",
                  "skills": data.get("skills") or [], "filled_positions": 0, "created_by": user["id"],
                  "created_by_name": user["name"], "created_at": ts, "updated_at": ts}
    await db.requisitions.insert_one(doc)
    await log_activity(user, "create", "requisition", doc["id"], f"{doc['code']} {doc['title']}", f"{doc['positions']} position(s)")
    for pid in (doc.get("recruiter_id"), doc.get("hiring_manager_id")):
        await notify(await user_ids_for_person(pid), "assignment", "New requisition assigned",
                     f"{doc['code']} · {doc['title']}", f"/requisitions/{doc['id']}")
    return (await enrich_reqs([{k: v for k, v in doc.items() if k != "_id"}]))[0]


async def closure_issues(req, data):
    issues = []
    active = await db.applications.count_documents({"requisition_id": req["id"], "status": {"$nin": list(INACTIVE)}})
    if active:
        issues.append(f"{active} candidate application(s) are still active or on hold — resolve them first")
    if await db.offers.count_documents({"requisition_id": req["id"], "status": {"$in": ["Draft", "Approval Pending", "Approved", "Released"]}}):
        issues.append("There are open offers pending a final outcome")
    if await db.joinings.count_documents({"requisition_id": req["id"], "status": {"$in": ["Pending", "Joining Confirmed", "Joining Deferred"]}}):
        issues.append("There are joining records pending confirmation")
    positions = data.get("positions", req.get("positions")) or 0
    if (req.get("filled_positions") or 0) < positions and not (data.get("closure_reason") or req.get("closure_reason") or "").strip():
        issues.append("Not all positions are filled — a closure reason is required")
    return issues


@router.get("/requisitions/{rid}")
async def get_requisition(rid: str, user=Depends(require("req.view"))):
    scope = await get_scope(user)
    req = (await enrich_reqs([await get_visible("requisitions", "req", rid, scope)]))[0]
    if can(user, "app.view"):
        req["applications"] = await list_applications(user, {"requisition_id": rid})
    return req


@router.put("/requisitions/{rid}")
async def update_requisition(rid: str, body: ReqIn, user=Depends(require("req.manage"))):
    req = await get_visible("requisitions", "req", rid, await get_scope(user))
    data = body.model_dump(exclude_unset=True)
    await validate_req(data)
    if data.get("status") == "Closed" and req["status"] != "Closed":
        issues = await closure_issues(req, data)
        if issues:
            raise HTTPException(400, " · ".join(issues))
        data["closed_at"] = now_iso()
    if "positions" in data and data["positions"] < (req.get("filled_positions") or 0):
        raise HTTPException(400, "Positions cannot be fewer than already filled positions")
    data["updated_at"] = now_iso()
    await db.requisitions.update_one({"id": rid}, {"$set": data})
    mm = await masters_map()
    changes = []
    for k, v in data.items():
        if k in REQ_LABELS and req.get(k) != v:
            fmt = (lambda x: mm.get(x, x)) if k.endswith("_id") else (lambda x: x)
            changes.append(f"{REQ_LABELS[k]}: {fmt(req.get(k)) or '—'} → {fmt(v) or '—'}")
    if changes:
        await log_activity(user, "update", "requisition", rid, f"{req['code']} {req['title']}", "; ".join(changes))
    for k in ("recruiter_id", "hiring_manager_id"):
        if data.get(k) and data[k] != req.get(k):
            await notify(await user_ids_for_person(data[k]), "assignment", "New requisition assigned",
                         f"{req['code']} · {data.get('title', req['title'])}", f"/requisitions/{rid}")
    return await get_requisition(rid, user)


# ---------- candidates ----------
class CandIn(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    current_company: Optional[str] = None
    current_designation: Optional[str] = None
    current_location: Optional[str] = None
    total_exp: Optional[float] = None
    relevant_exp: Optional[float] = None
    qualification: Optional[str] = None
    current_ctc: Optional[float] = None
    expected_ctc: Optional[float] = None
    notice_period: Optional[str] = None
    notice_days: Optional[int] = None
    last_working_day: Optional[str] = None
    available_from: Optional[str] = None
    source_id: Optional[str] = None
    partner_id: Optional[str] = None
    recruiter_id: Optional[str] = None
    remarks: Optional[str] = None
    skills: Optional[List[str]] = None
    requisition_id: Optional[str] = None
    force: Optional[bool] = False


def norm_phone(p):
    d = re.sub(r"\D", "", str(p or ""))
    return d[-10:] if len(d) >= 10 else d


async def find_duplicates(email, phone, exclude=None):
    ors = []
    if email:
        ors.append({"email": email.strip().lower()})
    if norm_phone(phone):
        ors.append({"phone_norm": norm_phone(phone)})
    if not ors:
        return []
    q = {"$or": ors}
    if exclude:
        q["id"] = {"$ne": exclude}
    return await db.candidates.find(q, {"_id": 0, "id": 1, "code": 1, "name": 1, "email": 1, "phone": 1}).to_list(10)


@router.get("/candidates/check-duplicates")
async def check_dups(email: Optional[str] = None, phone: Optional[str] = None, exclude_id: Optional[str] = None,
                     user=Depends(require("cand.view"))):
    return await find_duplicates(email, phone, exclude_id)


async def enrich_cands(cands):
    mm = await masters_map()
    ids = [c["id"] for c in cands]
    apps = {}
    async for a in db.applications.find({"candidate_id": {"$in": ids}}, {"_id": 0, "candidate_id": 1, "status": 1,
                                                                          "requisition_id": 1, "updated_at": 1}):
        apps.setdefault(a["candidate_id"], []).append(a)
    reqs = {r["id"]: r["title"] async for r in db.requisitions.find({}, {"id": 1, "title": 1})}
    for c in cands:
        for k in ("source", "partner", "recruiter"):
            c[k] = mm.get(c.get(f"{k}_id"))
        al = sorted(apps.get(c["id"], []), key=lambda a: a.get("updated_at") or "", reverse=True)
        c["applications_count"] = len(al)
        c["latest_status"] = al[0]["status"] if al else None
        c["roles"] = ", ".join(dict.fromkeys(reqs.get(a["requisition_id"], "") for a in al)) or c.get("legacy_role")
        c["statuses"] = [a["status"] for a in al]
    return cands


async def list_candidates(user, f):
    scope = await get_scope(user)
    q = dict(scope.q("cand"))
    for k in ("source_id", "partner_id", "recruiter_id"):
        if f.get(k):
            q[k] = f[k]
    if f.get("q"):
        s = f["q"]
        q["$or"] = [{k: rx(s)} for k in ("name", "email", "phone", "current_company", "code", "legacy_role", "current_designation")]
    rng = {"total_exp": ("min_exp", "max_exp"), "current_ctc": ("min_ctc", "max_ctc"), "expected_ctc": ("min_ectc", "max_ectc")}
    for field, (lo, hi) in rng.items():
        cond = {}
        if f.get(lo) not in (None, ""):
            cond["$gte"] = float(f[lo])
        if f.get(hi) not in (None, ""):
            cond["$lte"] = float(f[hi])
        if cond:
            q[field] = cond
    if f.get("max_notice") not in (None, ""):
        q["notice_days"] = {"$lte": int(f["max_notice"])}
    if f.get("status") or f.get("requisition_id"):
        aq = {k: f[k] for k in ("status", "requisition_id") if f.get(k)}
        cids = {a["candidate_id"] async for a in db.applications.find(aq, {"candidate_id": 1})}
        q["id"] = {"$in": list(cids & set(scope.cand_ids)) if not scope.full else list(cids)}
    cands = await db.candidates.find(q, {"_id": 0}).sort("created_at", -1).to_list(10000)
    return await enrich_cands(cands)


@router.get("/candidates")
async def get_candidates(request: Request, user=Depends(require("cand.view"))):
    return await list_candidates(user, dict(request.query_params))


async def create_application(user, cand, req, note="", status="New"):
    if req["status"] not in ("Open", "On Hold"):
        raise HTTPException(400, f"Requisition {req['code']} is {req['status']} — candidates can only be linked to open requisitions")
    if await db.applications.find_one({"candidate_id": cand["id"], "requisition_id": req["id"], "closed": False}):
        raise HTTPException(409, "This candidate already has an active application for this requisition")
    ts = now_iso()
    app = {"id": new_id(), "code": await next_code("APP", 5), "candidate_id": cand["id"], "requisition_id": req["id"],
           "recruiter_id": req.get("recruiter_id") or cand.get("recruiter_id"), "status": status,
           "stage_entered_at": ts, "closed": status in INACTIVE, "created_at": ts, "updated_at": ts, "created_by": user["id"],
           "history": [{"status": status, "from": None, "at": ts, "by": user["name"], "reason": "", "auto": False, "note": note}]}
    await db.applications.insert_one(app)
    await log_activity(user, "application_create", "application", app["id"], f"{cand['name']} · {app['code']}",
                       f"Linked to {req['code']} {req['title']}")
    await notify(await user_ids_for_person(req.get("hiring_manager_id")), "stage", "New candidate for your requisition",
                 f"{cand['name']} → {req['title']}", f"/candidates/{cand['id']}")
    app.pop("_id", None)
    return app


def cand_fields(data):
    if data.get("email"):
        data["email"] = data["email"].strip().lower()
    if "phone" in data:
        data["phone_norm"] = norm_phone(data.get("phone"))
    if data.get("notice_period") and data.get("notice_days") is None:
        m = re.search(r"\d+", data["notice_period"])
        mult = 30 if re.search(r"month", data["notice_period"], re.I) else 1
        data["notice_days"] = int(m.group()) * mult if m else (0 if re.search(r"immediate", data["notice_period"], re.I) else None)
    return data


@router.post("/candidates")
async def create_candidate(body: CandIn, user=Depends(require("cand.manage"))):
    data = body.model_dump()
    force, req_id = data.pop("force"), data.pop("requisition_id")
    if not (data.get("name") or "").strip():
        raise HTTPException(400, "Full name is required")
    if not data.get("email") and not data.get("phone"):
        raise HTTPException(400, "Provide at least an email or mobile number")
    dups = await find_duplicates(data.get("email"), data.get("phone"))
    if dups and not force:
        raise HTTPException(409, {"message": "Potential duplicate candidate found", "duplicates": dups})
    if user["role"] == "recruiter" and not data.get("recruiter_id"):
        mine = await person_ids(user, "recruiter")
        data["recruiter_id"] = mine[0] if mine else None
    ts = now_iso()
    doc = cand_fields(data) | {"id": new_id(), "code": await next_code("CAN", 5), "name": data["name"].strip(),
                               "skills": data.get("skills") or [], "created_by": user["id"], "created_at": ts, "updated_at": ts}
    req = await get_visible("requisitions", "req", req_id, await get_scope(user)) if req_id else None
    await db.candidates.insert_one(doc)
    doc.pop("_id", None)
    await log_activity(user, "create", "candidate", doc["id"], f"{doc['code']} {doc['name']}", "Duplicate warning overridden" if dups else "")
    if req:
        await create_application(user, doc, req)
    return doc


@router.get("/candidates/{cid}")
async def get_candidate(cid: str, user=Depends(require("cand.view"))):
    scope = await get_scope(user)
    c = (await enrich_cands([await get_visible("candidates", "cand", cid, scope)]))[0]
    c["applications"] = await list_applications(user, {"candidate_id": cid}) if can(user, "app.view") else []
    iq = {"candidate_id": cid, **scope.q("interview")}
    c["interviews"] = await db.interviews.find(iq, {"_id": 0}).sort("date", -1).to_list(200)
    c["offers"] = await db.offers.find({"candidate_id": cid, **scope.q("offer")}, {"_id": 0}).to_list(50) if can(user, "offer.view") else []
    c["joinings"] = await db.joinings.find({"candidate_id": cid, **scope.q("offer")}, {"_id": 0}).to_list(50) if can(user, "joining.view") else []
    c["files"] = await db.files.find({"entity": "candidate", "entity_id": cid, "is_deleted": False}, {"_id": 0, "path": 0}).to_list(50)
    return c


@router.put("/candidates/{cid}")
async def update_candidate(cid: str, body: CandIn, user=Depends(require("cand.manage"))):
    c = await get_visible("candidates", "cand", cid, await get_scope(user))
    data = body.model_dump(exclude_unset=True)
    force = data.pop("force", False)
    data.pop("requisition_id", None)
    if "name" in data and not (data["name"] or "").strip():
        raise HTTPException(400, "Full name is required")
    dups = await find_duplicates(data.get("email"), data.get("phone"), cid) if ("email" in data or "phone" in data) else []
    if dups and not force:
        raise HTTPException(409, {"message": "Another candidate has this email or mobile number", "duplicates": dups})
    data = cand_fields(data)
    data["updated_at"] = now_iso()
    await db.candidates.update_one({"id": cid}, {"$set": data})
    changed = [k for k, v in data.items() if c.get(k) != v and k not in ("updated_at", "phone_norm", "notice_days")]
    await log_activity(user, "update", "candidate", cid, f"{c['code']} {c['name']}", "Updated: " + ", ".join(changed))
    return await get_candidate(cid, user)


# ---------- applications / pipeline ----------
async def list_applications(user, f):
    scope = await get_scope(user)
    q = dict(scope.q("app"))
    for k in ("requisition_id", "candidate_id", "recruiter_id", "status"):
        if f.get(k):
            q[k] = f[k]
    if f.get("active") == "true":
        q["closed"] = False
    apps = await db.applications.find(q, {"_id": 0}).sort("updated_at", -1).to_list(10000)
    cids = list({a["candidate_id"] for a in apps})
    rids = list({a["requisition_id"] for a in apps})
    cands = {c["id"]: c async for c in db.candidates.find({"id": {"$in": cids}}, {"_id": 0})}
    reqs = {r["id"]: r async for r in db.requisitions.find({"id": {"$in": rids}}, {"_id": 0})}
    mm = await masters_map()
    stale = (await get_settings()).get("stale_days", 7)
    out = []
    for a in apps:
        c, r = cands.get(a["candidate_id"], {}), reqs.get(a["requisition_id"], {})
        if f.get("department_id") and r.get("department_id") != f["department_id"]:
            continue
        if f.get("source_id") and c.get("source_id") != f["source_id"]:
            continue
        if f.get("partner_id") and c.get("partner_id") != f["partner_id"]:
            continue
        if f.get("q") and f["q"].lower() not in f"{c.get('name')} {c.get('email')} {r.get('title')} {a.get('code')}".lower():
            continue
        days = days_between(a["stage_entered_at"][:10], today())
        start = effective_start(r)
        a.update({"candidate_name": c.get("name"), "candidate_code": c.get("code"), "candidate_email": c.get("email"),
                  "candidate_phone": c.get("phone"), "current_company": c.get("current_company"),
                  "total_exp": c.get("total_exp"), "expected_ctc": c.get("expected_ctc"), "notice_period": c.get("notice_period"),
                  "requisition_code": r.get("code"), "requisition_title": r.get("title"),
                  "department": mm.get(r.get("department_id")), "department_id": r.get("department_id"),
                  "recruiter": mm.get(a.get("recruiter_id")), "source": mm.get(c.get("source_id")),
                  "partner": mm.get(c.get("partner_id")), "days_in_stage": days,
                  "stuck": a["status"] not in INACTIVE and days > stale,
                  "recruitment_age": days_between(start, today()) if start and a["status"] not in INACTIVE else None})
        a.pop("history", None) if f.get("slim") else None
        out.append(a)
    return out


@router.get("/applications")
async def get_applications(request: Request, user=Depends(require("app.view"))):
    return await list_applications(user, dict(request.query_params))


class AppIn(BaseModel):
    candidate_id: str
    requisition_id: str


@router.post("/applications")
async def add_application(body: AppIn, user=Depends(require("app.create"))):
    scope = await get_scope(user)
    cand = await get_visible("candidates", "cand", body.candidate_id, scope)
    req = await get_visible("requisitions", "req", body.requisition_id, scope)
    return await create_application(user, cand, req)


@router.get("/applications/{aid}")
async def get_application(aid: str, user=Depends(require("app.view"))):
    return await get_visible("applications", "app", aid, await get_scope(user))


class StatusIn(BaseModel):
    status: str
    reason: Optional[str] = None
    joining_date: Optional[str] = None


@router.post("/applications/{aid}/status")
async def move_application(aid: str, body: StatusIn, user=Depends(get_user)):
    if not (can(user, "app.move") or (can(user, "app.decide") and body.status in HM_ALLOWED)):
        raise HTTPException(403, "You are not permitted to move candidates to this stage")
    app = await get_visible("applications", "app", aid, await get_scope(user))
    if body.status == "Joined":
        if not body.joining_date:
            raise HTTPException(400, "Actual date of joining is required")
        from routes_offers import mark_joined
        await mark_joined(app, user, body.joining_date)
        return await get_visible("applications", "app", aid, await get_scope(user))
    return await set_app_status(app, body.status, user, body.reason)
