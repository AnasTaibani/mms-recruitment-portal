import os
import re
import uuid
from datetime import datetime, timezone, timedelta, date

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorClient

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
JWT_ALG = "HS256"

PIPELINE = ["New", "Screening", "Shortlisted", "Interview Scheduled", "Interview In Progress",
            "Interview Completed", "Selected", "Offer Approval Pending", "Offer Released", "Offer Accepted", "Joined"]
TERMINAL = ["CV Rejected", "Interview Rejected", "On Hold", "Candidate Withdrawn", "Offer Declined", "Offer Revoked", "No Show"]
ALL_STATUSES = PIPELINE + TERMINAL
IMPLIED_STAGE = {"CV Rejected": 1, "Interview Rejected": 4, "Offer Declined": 8, "Offer Revoked": 8, "No Show": 9}
INACTIVE = set(TERMINAL) | {"Joined"}
REQ_STATUSES = ["Draft", "Open", "On Hold", "Closed", "Cancelled"]
INTERVIEW_STATUSES = ["Scheduled", "Completed", "Rescheduled", "Cancelled", "No Show"]
INTERVIEW_MODES = ["Online", "In-Person", "Phone"]
OFFER_STATUSES = ["Draft", "Approval Pending", "Approved", "Released", "Accepted", "Declined", "Revoked", "Expired"]
JOINING_STATUSES = ["Pending", "Joining Confirmed", "Joined", "Joining Deferred", "No Show", "Cancelled"]
RECOMMENDATIONS = ["Strong Hire", "Hire", "Hold", "Reject"]
PAYMENT_STATUSES = ["Pending", "Partially Paid", "Paid"]
# Four personas. Recruiter = the former HR Admin + Recruiter combined (all recruitment operations & masters).
ROLES = {"super_admin": "Super Admin", "recruiter": "Recruiter", "management": "Management", "interviewer": "Interviewer"}
# Retired roles and what existing accounts are moved to on startup (never to a role with more access).
LEGACY_ROLES = {"hr_admin": "recruiter", "hiring_manager": "management"}
ROLE_PERSON = {"recruiter": "recruiter", "interviewer": "interviewer"}

ALL_PERMS = {"users.manage", "users.super", "masters.manage", "settings.manage", "req.view", "req.manage",
             "cand.view", "cand.manage", "app.view", "app.create", "app.move", "app.decide", "interview.view",
             "interview.manage", "feedback.submit", "feedback.view", "selection.decide", "offer.view", "offer.manage",
             "offer.approve", "joining.view", "joining.manage", "cost.view", "cost.manage", "analytics.view",
             "reports.export", "import.run", "activity.view"}
# Activity Log, Users & Roles, and Master Data & Settings are for the Super Admin only.
SUPER_ONLY = {"users.super", "users.manage", "masters.manage", "settings.manage", "activity.view"}
PERMS = {
    "super_admin": ALL_PERMS,
    "recruiter": ALL_PERMS - SUPER_ONLY,
    "interviewer": {"req.view", "cand.view", "interview.view", "feedback.submit"},
    "management": {"req.view", "cand.view", "app.view", "interview.view", "feedback.view", "offer.view",
                   "joining.view", "cost.view", "analytics.view", "reports.export"},
}
FULL_SCOPE = {"super_admin", "recruiter", "management"}
HM_ALLOWED = {"Shortlisted", "CV Rejected", "On Hold", "Interview Rejected", "Selected"}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def today():
    return datetime.now(timezone.utc).date().isoformat()


def new_id():
    return str(uuid.uuid4())


async def next_code(prefix, width=4):
    doc = await db.counters.find_one_and_update({"_id": prefix}, {"$inc": {"seq": 1}}, upsert=True, return_document=True)
    return f"{prefix}-{str(doc['seq']).zfill(width)}"


def parse_date(v):
    if v in (None, "", "-"):
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d-%B-%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:19] if "T" in s else s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"\d+(\.\d+)?", str(v).replace(",", ""))
    return float(m.group()) if m else None


def days_between(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def hash_password(p):
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def verify_password(p, h):
    return bcrypt.checkpw(p.encode(), h.encode())


def make_token(uid, kind, ttl):
    payload = {"sub": uid, "type": kind, "exp": datetime.now(timezone.utc) + ttl}
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=JWT_ALG)


def public_user(u):
    return {k: u.get(k) for k in ("id", "email", "name", "role", "active", "phone", "designation",
                                  "must_change_password", "created_at", "last_login")} | {
        "role_label": ROLES.get(u.get("role")), "permissions": sorted(PERMS.get(u.get("role"), set()))}


async def get_user(request: Request):
    token = request.cookies.get("access_token")
    auth = request.headers.get("Authorization", "")
    if not token and auth.startswith("Bearer "):
        token = auth[7:]
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALG])
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Session expired")
    if payload.get("type") != "access":
        raise HTTPException(401, "Invalid token")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user or not user.get("active"):
        raise HTTPException(401, "Account inactive")
    return user


def can(user, perm):
    return perm in PERMS.get(user["role"], set())


def require(perm):
    async def dep(user=Depends(get_user)):
        if not can(user, perm):
            raise HTTPException(403, "You do not have permission for this action")
        return user
    return dep


async def person_ids(user, ptype):
    return [m["id"] async for m in db.masters.find({"type": ptype, "user_id": user["id"]}, {"id": 1})]


class Scope:
    def __init__(self, full=True, req_ids=(), app_ids=(), cand_ids=(), interviewer_ids=None):
        self.full = full
        self.req_ids, self.app_ids, self.cand_ids = list(req_ids), list(app_ids), list(cand_ids)
        self.interviewer_ids = interviewer_ids

    def q(self, kind):
        if self.full:
            return {}
        if kind == "req":
            return {"id": {"$in": self.req_ids}}
        if kind == "cand":
            return {"id": {"$in": self.cand_ids}}
        if kind == "app":
            return {"id": {"$in": self.app_ids}}
        if kind == "interview" and self.interviewer_ids is not None:
            return {"interviewer_ids": {"$in": self.interviewer_ids}}
        return {"application_id": {"$in": self.app_ids}}


async def _ids(coll, q, field="id"):
    return {d[field] async for d in db[coll].find(q, {field: 1}) if d.get(field)}


async def get_scope(user):
    role = user["role"]
    if role in FULL_SCOPE:
        return Scope()
    if role == "interviewer":
        iids = await person_ids(user, "interviewer")
        ivs = [d async for d in db.interviews.find({"interviewer_ids": {"$in": iids}},
                                                    {"application_id": 1, "candidate_id": 1, "requisition_id": 1})]
        return Scope(False, {i["requisition_id"] for i in ivs}, {i["application_id"] for i in ivs},
                     {i["candidate_id"] for i in ivs}, iids)
    return Scope(False, set(), set(), set())  # unknown / retired role: sees nothing


async def get_visible(coll, kind, rid, scope):
    doc = await db[coll].find_one({"$and": [{"id": rid}, scope.q(kind)]}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Record not found")
    return doc


async def masters_map():
    return {m["id"]: m["name"] async for m in db.masters.find({}, {"id": 1, "name": 1})}


async def user_ids_for_person(pid):
    if not pid:
        return []
    m = await db.masters.find_one({"id": pid}, {"user_id": 1})
    return [m["user_id"]] if m and m.get("user_id") else []


async def admin_user_ids():
    return [u["id"] async for u in db.users.find({"role": {"$in": ["super_admin", "recruiter"]}, "active": True}, {"id": 1})]


async def log_activity(user, action, entity, entity_id, label="", details=""):
    await db.activity.insert_one({"id": new_id(), "at": now_iso(), "user_id": user["id"] if user else None,
                                  "user_name": user["name"] if user else "System", "action": action,
                                  "entity": entity, "entity_id": entity_id, "label": label, "details": details})


async def notify(user_ids, kind, title, message, link="", key=None):
    for uid in set(user_ids or []):
        if key and await db.notifications.find_one({"user_id": uid, "key": key}):
            continue
        await db.notifications.insert_one({"id": new_id(), "user_id": uid, "kind": kind, "title": title,
                                           "message": message, "link": link, "key": key, "read": False,
                                           "created_at": now_iso()})


async def get_settings():
    s = await db.settings.find_one({"key": "general"}, {"_id": 0})
    return s or {}


async def set_app_status(app, status, user, reason=None, auto=False, note=""):
    if status not in ALL_STATUSES:
        raise HTTPException(400, "Unknown status")
    if status == app["status"]:
        return app
    if not auto:
        if app["status"] == "Joined":
            raise HTTPException(400, "Joined applications are closed")
        trans = (await get_settings()).get("transitions", {})
        if status not in trans.get(app["status"], ALL_STATUSES):
            raise HTTPException(400, f"Transition {app['status']} → {status} is not permitted")
        if status in TERMINAL and not (reason or "").strip():
            raise HTTPException(400, "A reason is required for this status")
    ts = now_iso()
    entry = {"status": status, "from": app["status"], "at": ts, "by": user["name"] if user else "System",
             "reason": reason or "", "auto": auto, "note": note}
    upd = {"status": status, "stage_entered_at": ts, "updated_at": ts, "closed": status in INACTIVE}
    await db.applications.update_one({"id": app["id"]}, {"$set": upd, "$push": {"history": entry}})
    cand = await db.candidates.find_one({"id": app["candidate_id"]}, {"name": 1})
    label = f"{cand['name'] if cand else ''} · {app.get('code', '')}"
    await log_activity(user, "status_change", "application", app["id"], label,
                       f"{app['status']} → {status}" + (f" ({reason})" if reason else "") + (" [auto]" if auto else ""))
    targets = await user_ids_for_person(app.get("recruiter_id"))
    if user:
        targets = [t for t in targets if t != user["id"]]
    await notify(targets, "stage", "Candidate stage updated", f"{label}: {app['status']} → {status}",
                 f"/candidates/{app['candidate_id']}")
    app.update(upd)
    return app


async def recount_filled(req_id):
    n = await db.joinings.count_documents({"requisition_id": req_id, "status": "Joined"})
    await db.requisitions.update_one({"id": req_id}, {"$set": {"filled_positions": n}})
    return n


def effective_start(req):
    crf, init = req.get("crf_date"), req.get("initiation_date")
    if crf and init:
        return crf if init >= crf else init
    return crf or init
