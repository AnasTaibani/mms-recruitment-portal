import asyncio
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, File, Form
from pydantic import BaseModel, Field

from workflow import static_matrix
from core import (db, get_user, require, can, make_token, hash_password, verify_password, public_user, now_iso,
                  new_id, log_activity, get_settings, get_scope, get_visible, ROLES, ROLE_PERSON, PIPELINE, TERMINAL,
                  ALL_STATUSES, REQ_STATUSES, INTERVIEW_STATUSES, INTERVIEW_MODES, OFFER_STATUSES, JOINING_STATUSES,
                  RECOMMENDATIONS, PAYMENT_STATUSES)
import jwt
import os
from storage import put_object, get_object, APP_NAME

router = APIRouter(prefix="/api")

MASTER_TYPES = {"department": "Departments", "job_title": "Job Titles / Roles", "location": "Locations",
                "source": "Recruitment Sources", "partner": "Recruitment Partners / Consultancies",
                "recruiter": "Recruiters", "hiring_manager": "Hiring Managers", "interviewer": "Interviewers",
                "round_type": "Interview Round Types", "rejection_reason": "Rejection Reasons",
                "priority": "Priority Levels", "employment_type": "Employment Types",
                "cost_category": "Cost Categories", "document": "Joining Document Checklist"}


def set_cookies(resp, uid):
    opts = dict(httponly=True, secure=True, samesite="none", path="/")
    access, refresh = make_token(uid, "access", timedelta(hours=1)), make_token(uid, "refresh", timedelta(days=7))
    resp.set_cookie("access_token", access, max_age=3600, **opts)
    resp.set_cookie("refresh_token", refresh, max_age=604800, **opts)
    # also returned in the body so the frontend can send them as headers when the browser blocks cookies
    return {"access_token": access, "refresh_token": refresh}


class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/auth/login")
async def login(body: LoginIn, request: Request, response: Response):
    email = body.email.strip().lower()
    ident = f"{request.client.host if request.client else ''}:{email}"
    att = await db.login_attempts.find_one({"identifier": ident})
    lock_since = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    if att and att.get("count", 0) >= 5 and att.get("last", "") > lock_since:
        raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes.")
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user or not verify_password(body.password, user["password_hash"]):
        await db.login_attempts.update_one({"identifier": ident}, {"$inc": {"count": 1}, "$set": {"last": now_iso()}}, upsert=True)
        raise HTTPException(401, "Invalid email or password")
    if not user.get("active"):
        raise HTTPException(403, "Your account is deactivated. Contact your administrator.")
    await db.login_attempts.delete_many({"identifier": ident})
    await db.users.update_one({"id": user["id"]}, {"$set": {"last_login": now_iso()}})
    tokens = set_cookies(response, user["id"])
    await log_activity(user, "login", "user", user["id"], user["email"])
    return public_user(user) | tokens


@router.post("/auth/logout")
async def logout(response: Response):
    for k in ("access_token", "refresh_token"):
        response.delete_cookie(k, path="/", secure=True, samesite="none")
    return {"ok": True}


@router.post("/auth/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token") or request.headers.get("X-Refresh-Token")
    if not token:
        raise HTTPException(401, "No session")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=["HS256"])
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Session expired")
    user = await db.users.find_one({"id": payload.get("sub")}, {"_id": 0})
    if payload.get("type") != "refresh" or not user or not user.get("active"):
        raise HTTPException(401, "Session expired")
    return public_user(user) | set_cookies(response, user["id"])


@router.get("/auth/me")
async def me(user=Depends(get_user)):
    return public_user(user)


class PasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


@router.post("/auth/change-password")
async def change_password(body: PasswordIn, user=Depends(get_user)):
    full = await db.users.find_one({"id": user["id"]})
    if not verify_password(body.current_password, full["password_hash"]):
        raise HTTPException(400, "Current password is incorrect")
    await db.users.update_one({"id": user["id"]}, {"$set": {"password_hash": hash_password(body.new_password),
                                                            "must_change_password": False}})
    await log_activity(user, "password_change", "user", user["id"], user["email"])
    return {"ok": True}


class ProfileIn(BaseModel):
    name: str = Field(min_length=2)
    phone: Optional[str] = None
    designation: Optional[str] = None


@router.put("/auth/profile")
async def update_profile(body: ProfileIn, user=Depends(get_user)):
    await db.users.update_one({"id": user["id"]}, {"$set": body.model_dump()})
    return public_user(await db.users.find_one({"id": user["id"]}, {"_id": 0}))


# ---------- users ----------
class UserIn(BaseModel):
    email: str
    name: str = Field(min_length=2)
    role: str
    password: str = Field(min_length=8)
    phone: Optional[str] = None
    designation: Optional[str] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None
    phone: Optional[str] = None
    designation: Optional[str] = None


async def sync_person(user):
    ptype = ROLE_PERSON.get(user["role"])
    if not ptype:
        return
    if await db.masters.find_one({"type": ptype, "user_id": user["id"]}):
        return
    existing = await db.masters.find_one({"type": ptype, "user_id": None,
                                          "name": {"$regex": f"^{re.escape(user['name'].strip())}$", "$options": "i"}})
    if existing:
        await db.masters.update_one({"id": existing["id"]}, {"$set": {"user_id": user["id"], "email": user["email"]}})
    else:
        await db.masters.insert_one({"id": new_id(), "type": ptype, "name": user["name"], "email": user["email"],
                                     "user_id": user["id"], "active": True, "created_at": now_iso()})


def guard_role_change(actor, target_role=None, target_user=None):
    if (target_role == "super_admin" or (target_user and target_user["role"] == "super_admin")) and not can(actor, "users.super"):
        raise HTTPException(403, "Only a Super Admin can manage Super Admin accounts")
    if target_role and target_role not in ROLES:
        raise HTTPException(400, "Invalid role")


@router.get("/users")
async def list_users(user=Depends(require("users.manage"))):
    return [public_user(u) async for u in db.users.find({}, {"_id": 0, "password_hash": 0}).sort("name", 1)]


@router.post("/users")
async def create_user(body: UserIn, user=Depends(require("users.manage"))):
    guard_role_change(user, body.role)
    email = body.email.strip().lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(409, "A user with this email already exists")
    doc = {"id": new_id(), "email": email, "name": body.name.strip(), "role": body.role, "active": True,
           "phone": body.phone, "designation": body.designation, "password_hash": hash_password(body.password),
           "must_change_password": True, "created_at": now_iso()}
    await db.users.insert_one(doc)
    await sync_person(doc)
    await log_activity(user, "user_create", "user", doc["id"], email, ROLES[body.role])
    return public_user(doc)


@router.put("/users/{uid}")
async def update_user(uid: str, body: UserUpdate, user=Depends(require("users.manage"))):
    target = await db.users.find_one({"id": uid}, {"_id": 0})
    if not target:
        raise HTTPException(404, "User not found")
    data = body.model_dump(exclude_unset=True)
    guard_role_change(user, data.get("role"), target)
    if uid == user["id"] and (data.get("active") is False or (data.get("role") and data["role"] != user["role"])):
        raise HTTPException(400, "You cannot deactivate or change the role of your own account")
    await db.users.update_one({"id": uid}, {"$set": data})
    target.update(data)
    await sync_person(target)
    await log_activity(user, "user_update", "user", uid, target["email"], ", ".join(f"{k}={v}" for k, v in data.items()))
    return public_user(target)


class ResetIn(BaseModel):
    password: str = Field(min_length=8)


@router.post("/users/{uid}/reset-password")
async def reset_user_password(uid: str, body: ResetIn, user=Depends(require("users.manage"))):
    target = await db.users.find_one({"id": uid})
    if not target:
        raise HTTPException(404, "User not found")
    guard_role_change(user, None, target)
    await db.users.update_one({"id": uid}, {"$set": {"password_hash": hash_password(body.password), "must_change_password": True}})
    await log_activity(user, "password_reset", "user", uid, target["email"])
    return {"ok": True}


# ---------- masters & settings ----------
class MasterIn(BaseModel):
    type: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    skill_area: Optional[str] = None
    user_id: Optional[str] = None
    active: Optional[bool] = None


@router.get("/masters")
async def list_masters(user=Depends(get_user)):
    return await db.masters.find({}, {"_id": 0}).sort([("type", 1), ("name", 1)]).to_list(5000)


@router.post("/masters")
async def create_master(body: MasterIn, user=Depends(require("masters.manage"))):
    if body.type not in MASTER_TYPES or not (body.name or "").strip():
        raise HTTPException(400, "Type and name are required")
    name = body.name.strip()
    if await db.masters.find_one({"type": body.type, "name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}):
        raise HTTPException(409, f"'{name}' already exists in {MASTER_TYPES[body.type]}")
    doc = body.model_dump() | {"id": new_id(), "name": name, "active": True, "created_at": now_iso()}
    await db.masters.insert_one(doc)
    await log_activity(user, "master_create", "master", doc["id"], name, MASTER_TYPES[body.type])
    doc.pop("_id", None)
    return doc


@router.put("/masters/{mid}")
async def update_master(mid: str, body: MasterIn, user=Depends(require("masters.manage"))):
    data = body.model_dump(exclude_unset=True)
    data.pop("type", None)
    m = await db.masters.find_one({"id": mid}, {"_id": 0})
    if not m:
        raise HTTPException(404, "Not found")
    if data.get("user_id") and await db.masters.find_one({"type": m["type"], "user_id": data["user_id"], "id": {"$ne": mid}}):
        raise HTTPException(409, "That user is already linked to another entry")
    await db.masters.update_one({"id": mid}, {"$set": data})
    await log_activity(user, "master_update", "master", mid, m["name"], ", ".join(f"{k}={v}" for k, v in data.items()))
    return {**m, **data}


class SettingsIn(BaseModel):
    rating_scale: Optional[int] = None
    stale_days: Optional[int] = None
    offer_expiry_alert_days: Optional[int] = None
    transitions: Optional[dict] = None


@router.get("/meta")
async def meta(user=Depends(get_user)):
    s = await get_settings()
    return {"pipeline": PIPELINE, "terminal": TERMINAL, "req_statuses": REQ_STATUSES, "interview_statuses": INTERVIEW_STATUSES,
            "interview_modes": INTERVIEW_MODES, "offer_statuses": OFFER_STATUSES, "joining_statuses": JOINING_STATUSES,
            "recommendations": RECOMMENDATIONS, "payment_statuses": PAYMENT_STATUSES, "roles": ROLES,
            "master_types": MASTER_TYPES, "settings": {k: v for k, v in s.items() if k not in ("key", "previous_transitions")},
            "workflow_matrix": static_matrix(), "cost_statuses": ["Cost Recorded", "Invoice Pending", "No Recruitment Cost"]}


@router.put("/settings")
async def update_settings(body: SettingsIn, user=Depends(require("settings.manage"))):
    data = body.model_dump(exclude_unset=True)
    if "rating_scale" in data and data["rating_scale"] not in (3, 4, 5, 10):
        raise HTTPException(400, "Rating scale must be 3, 4, 5 or 10")
    if "transitions" in data:
        # settings can only narrow the defined workflow matrix, never open new paths
        m = static_matrix()
        data["transitions"] = {k: [s for s in v if s in m.get(k, [])] for k, v in data["transitions"].items() if k in ALL_STATUSES}
    await db.settings.update_one({"key": "general"}, {"$set": data}, upsert=True)
    await log_activity(user, "settings_update", "settings", "general", "System settings", ", ".join(data.keys()))
    return await get_settings()


# ---------- notifications & activity ----------
@router.get("/notifications")
async def my_notifications(user=Depends(get_user)):
    items = await db.notifications.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    unread = await db.notifications.count_documents({"user_id": user["id"], "read": False})
    return {"items": items, "unread": unread}


@router.post("/notifications/read-all")
async def read_all(user=Depends(get_user)):
    await db.notifications.update_many({"user_id": user["id"]}, {"$set": {"read": True}})
    return {"ok": True}


@router.post("/notifications/{nid}/read")
async def read_one(nid: str, user=Depends(get_user)):
    await db.notifications.update_one({"id": nid, "user_id": user["id"]}, {"$set": {"read": True}})
    return {"ok": True}


@router.get("/activity")
async def activity(entity: Optional[str] = None, q: Optional[str] = None, user_id: Optional[str] = None,
                   date_from: Optional[str] = None, date_to: Optional[str] = None, limit: int = 500,
                   user=Depends(require("activity.view"))):
    f = {}
    if entity:
        f["entity"] = entity
    if user_id:
        f["user_id"] = user_id
    if q:
        f["$or"] = [{"label": {"$regex": q, "$options": "i"}}, {"details": {"$regex": q, "$options": "i"}},
                    {"action": {"$regex": q, "$options": "i"}}]
    if date_from or date_to:
        f["at"] = {k: v for k, v in (("$gte", date_from), ("$lte", (date_to or "") + "T23:59:59")) if v and v != "T23:59:59"}
    return await db.activity.find(f, {"_id": 0}).sort("at", -1).to_list(min(limit, 2000))


ENTITY_KIND = {"requisition": ("requisitions", "req"), "candidate": ("candidates", "cand"), "application": ("applications", "app")}


@router.get("/activity/{entity}/{eid}")
async def entity_history(entity: str, eid: str, user=Depends(get_user)):
    if entity not in ENTITY_KIND:
        raise HTTPException(400, "Unsupported entity")
    coll, kind = ENTITY_KIND[entity]
    await get_visible(coll, kind, eid, await get_scope(user))
    ids = [eid]
    if entity == "candidate":
        ids += [a["id"] async for a in db.applications.find({"candidate_id": eid}, {"id": 1})]
    return await db.activity.find({"entity_id": {"$in": ids}}, {"_id": 0}).sort("at", -1).to_list(500)


# ---------- files ----------
ALLOWED = {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
           "doc": "application/msword"}


async def check_file_access(user, entity, eid, write):
    scope = await get_scope(user)
    if entity == "candidate":
        if write and not can(user, "cand.manage"):
            raise HTTPException(403, "Not permitted")
        return await get_visible("candidates", "cand", eid, scope)
    if entity == "offer":
        if not can(user, "offer.manage" if write else "offer.view"):
            raise HTTPException(403, "Not permitted")
        return await get_visible("offers", "offer", eid, scope)
    raise HTTPException(400, "Unsupported entity")


@router.post("/files")
async def upload_file(entity: str = Form(...), entity_id: str = Form(...), file: UploadFile = File(...), user=Depends(get_user)):
    await check_file_access(user, entity, entity_id, True)
    ext = (file.filename.rsplit(".", 1)[-1] if "." in file.filename else "").lower()
    if ext not in ALLOWED:
        raise HTTPException(400, "Only PDF and DOCX files are allowed")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(400, "File exceeds 10 MB")
    path = f"{APP_NAME}/{entity}/{entity_id}/{uuid.uuid4()}.{ext}"
    res = await asyncio.to_thread(put_object, path, data, ALLOWED[ext])
    doc = {"id": new_id(), "path": res["path"], "name": file.filename, "content_type": ALLOWED[ext], "size": len(data),
           "entity": entity, "entity_id": entity_id, "uploaded_by": user["name"], "uploaded_at": now_iso(), "is_deleted": False}
    await db.files.insert_one(doc)
    ref = {"file_id": doc["id"], "name": file.filename, "uploaded_at": doc["uploaded_at"]}
    if entity == "candidate":
        await db.candidates.update_one({"id": entity_id}, {"$set": {"resume": ref, "updated_at": now_iso()}})
    else:
        await db.offers.update_one({"id": entity_id}, {"$set": {"document": ref}})
    await log_activity(user, "file_upload", entity, entity_id, file.filename)
    return ref


@router.get("/files/{fid}")
async def download_file(fid: str, user=Depends(get_user)):
    f = await db.files.find_one({"id": fid, "is_deleted": False}, {"_id": 0})
    if not f:
        raise HTTPException(404, "File not found")
    await check_file_access(user, f["entity"], f["entity_id"], False)
    data, _ = await asyncio.to_thread(get_object, f["path"])
    return Response(content=data, media_type=f["content_type"],
                    headers={"Content-Disposition": f'attachment; filename="{f["name"]}"'})


# ---------- data cleanup (Super Admin) ----------
# Transactional recruitment data. Everything else (users, masters, settings, auth, schema/indexes) is preserved.
RECRUITMENT_COLLECTIONS = {
    "requisitions": "Requisitions", "candidates": "Candidates", "applications": "Candidate applications",
    "interviews": "Interviews", "feedback": "Interview feedback", "selections": "Selection decisions",
    "offers": "Offers", "joinings": "Joining records", "costs": "Recruitment costs", "notifications": "Notifications",
    "activity": "Activity logs", "files": "Uploaded file records (CVs / offer letters)", "import_batches": "Import batches",
    "counters": "ID counters (REQ-/CAN-/APP- numbering restarts at 0001)",
}
CONFIRM_PHRASE = "DELETE ALL RECRUITMENT DATA"
TEST_USER_Q = {"$or": [{"name": {"$regex": "^TEST_"}}, {"email": {"$regex": "@mms\\.test$"}}], "role": {"$ne": "super_admin"}}


def environment():
    host = re.sub(r"//[^@/]*@", "//***@", os.environ.get("MONGO_URL", ""))  # never expose credentials
    return {"environment": os.environ.get("APP_ENV") or "preview", "database": os.environ["DB_NAME"], "mongo_host": host}


async def cleanup_counts():
    counts = {c: await db[c].count_documents({}) for c in RECRUITMENT_COLLECTIONS}
    counts["test_users"] = await db.users.count_documents(TEST_USER_Q)
    counts["test_master_entries"] = await db.masters.count_documents({"name": {"$regex": "^TEST_"}})
    return counts


@router.get("/admin/data-status")
async def data_status(user=Depends(require("users.super"))):
    preserved = {"users": await db.users.count_documents({}) - await db.users.count_documents(TEST_USER_Q),
                 "masters": await db.masters.count_documents({"name": {"$not": {"$regex": "^TEST_"}}}),
                 "settings": await db.settings.count_documents({})}
    return environment() | {"counts": await cleanup_counts(), "labels": RECRUITMENT_COLLECTIONS, "preserved": preserved,
                            "masters_created_by_import": await db.masters.count_documents({"notes": "Created by Excel import"}),
                            "confirm_phrase": CONFIRM_PHRASE}


class CleanupIn(BaseModel):
    confirm: str
    database: str


async def run_cleanup(actor=None):
    """Deletes all transactional recruitment data and test accounts; returns per-collection deleted counts."""
    deleted = {}
    for c in RECRUITMENT_COLLECTIONS:
        deleted[c] = (await db[c].delete_many({})).deleted_count
    ids = [u["id"] async for u in db.users.find(TEST_USER_Q, {"id": 1})]
    deleted["test_users"] = (await db.users.delete_many({"id": {"$in": ids}})).deleted_count
    deleted["test_master_entries"] = (await db.masters.delete_many({"$or": [{"name": {"$regex": "^TEST_"}}, {"user_id": {"$in": ids}}]})).deleted_count
    # referential integrity: master entries linked to a user that no longer exists are unlinked (kept, not deleted)
    live = [u["id"] async for u in db.users.find({}, {"id": 1})]
    deleted["master_links_cleared"] = (await db.masters.update_many({"user_id": {"$nin": [None] + live}}, {"$set": {"user_id": None}})).modified_count
    remaining = await cleanup_counts()
    return deleted, remaining


@router.post("/admin/cleanup")
async def cleanup(body: CleanupIn, user=Depends(require("users.super"))):
    if body.confirm.strip() != CONFIRM_PHRASE:
        raise HTTPException(400, f"Type '{CONFIRM_PHRASE}' to confirm")
    if body.database.strip() != os.environ["DB_NAME"]:
        raise HTTPException(400, f"Database name does not match the connected database ({os.environ['DB_NAME']})")
    deleted, remaining = await run_cleanup(user)
    await log_activity(user, "data_cleanup", "system", "cleanup", "Recruitment data cleared",
                       ", ".join(f"{k}: {v}" for k, v in deleted.items()))
    return environment() | {"deleted": deleted, "remaining": remaining, "verified": not any(remaining.values()),
                            "total_deleted": sum(v for k, v in deleted.items() if k != "master_links_cleared")}
