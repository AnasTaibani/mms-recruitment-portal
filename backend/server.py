from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

import asyncio
import logging
import os
from contextlib import suppress
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI
from pymongo import ASCENDING, DESCENDING, IndexModel
from starlette.middleware.cors import CORSMiddleware

from core import (db, client, hash_password, new_id, now_iso, today, notify, user_ids_for_person, admin_user_ids,
                  days_between, INACTIVE, PIPELINE, TERMINAL, ALL_STATUSES)
from storage import init_storage
import routes_admin
import routes_recruit
import routes_interviews
import routes_offers
import routes_analytics
import routes_import

logger = logging.getLogger("mms")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

INDEXES = {
    "users": [IndexModel([("email", ASCENDING)], unique=True, name="email"), IndexModel([("id", ASCENDING)], unique=True, name="id")],
    "masters": [IndexModel([("type", ASCENDING), ("name", ASCENDING)], name="type_name"), IndexModel([("id", ASCENDING)], unique=True, name="id"),
                IndexModel([("user_id", ASCENDING)], name="user_id")],
    "requisitions": [IndexModel([("id", ASCENDING)], unique=True, name="id"), IndexModel([("status", ASCENDING)], name="status"),
                     IndexModel([("recruiter_id", ASCENDING)], name="recruiter"), IndexModel([("hiring_manager_id", ASCENDING)], name="hm")],
    "candidates": [IndexModel([("id", ASCENDING)], unique=True, name="id"), IndexModel([("email", ASCENDING)], name="email"),
                   IndexModel([("phone_norm", ASCENDING)], name="phone"), IndexModel([("recruiter_id", ASCENDING)], name="recruiter")],
    "applications": [IndexModel([("id", ASCENDING)], unique=True, name="id"), IndexModel([("candidate_id", ASCENDING)], name="cand"),
                     IndexModel([("requisition_id", ASCENDING)], name="req"), IndexModel([("status", ASCENDING)], name="status")],
    "interviews": [IndexModel([("id", ASCENDING)], unique=True, name="id"), IndexModel([("application_id", ASCENDING)], name="app"),
                   IndexModel([("interviewer_ids", ASCENDING), ("date", ASCENDING)], name="ivr_date")],
    "feedback": [IndexModel([("interview_id", ASCENDING), ("interviewer_id", ASCENDING)], unique=True, name="iv_ivr")],
    "offers": [IndexModel([("id", ASCENDING)], unique=True, name="id"), IndexModel([("application_id", ASCENDING)], name="app")],
    "joinings": [IndexModel([("id", ASCENDING)], unique=True, name="id"), IndexModel([("application_id", ASCENDING)], name="app")],
    "costs": [IndexModel([("id", ASCENDING)], unique=True, name="id"), IndexModel([("invoice_date", DESCENDING)], name="date")],
    "notifications": [IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_date"), IndexModel([("user_id", ASCENDING), ("key", ASCENDING)], name="user_key")],
    "activity": [IndexModel([("entity_id", ASCENDING)], name="entity"), IndexModel([("at", DESCENDING)], name="at")],
    "login_attempts": [IndexModel([("identifier", ASCENDING)], name="identifier")],
    "files": [IndexModel([("id", ASCENDING)], unique=True, name="id")],
}

DEFAULT_MASTERS = {
    "source": ["LinkedIn", "Referral", "Direct Contact", "Naukri", "Internal Database", "Consultant", "Executive Search", "Walk-in"],
    "round_type": ["Technical", "HR", "Managerial", "Functional"],
    "priority": ["Critical", "High", "Medium", "Low"],
    "employment_type": ["Full-time", "Contract", "Internship"],
    "cost_category": ["Recruiter Fees", "Recruitment Partner / Consultancy Fees"],
    "rejection_reason": ["Skills mismatch", "Experience mismatch", "Compensation too high", "Notice period too long", "Communication", "Culture fit", "Not reachable"],
    "document": ["Signed offer letter", "Resignation acceptance / relieving letter", "Last 3 payslips", "Educational certificates", "ID & address proof", "PAN card", "Bank details"],
}


def default_transitions():
    t = {}
    for s in ALL_STATUSES:
        t[s] = [x for x in ALL_STATUSES if x != s] if s != "Joined" else []
    return t


async def migrate_roles():
    """Move accounts on retired roles (HR Admin, Hiring Manager) to the four current personas."""
    from core import LEGACY_ROLES
    for old, new in LEGACY_ROLES.items():
        users = [u async for u in db.users.find({"role": old}, {"_id": 0})]
        for u in users:
            await db.users.update_one({"id": u["id"]}, {"$set": {"role": new, "previous_role": old}})
            await routes_admin.sync_person(u | {"role": new})
        if users:
            logger.info("roles: moved %d %s account(s) to %s", len(users), old, new)


async def seed():
    await migrate_roles()
    for coll, models in INDEXES.items():
        for m in models:
            try:
                await db[coll].create_indexes([m])
            except Exception as exc:
                logger.error("index %s.%s: %s", coll, m.document["name"], exc)
    for mtype, names in DEFAULT_MASTERS.items():
        if not await db.masters.find_one({"type": mtype}):
            await db.masters.insert_many([{"id": new_id(), "type": mtype, "name": n, "active": True, "user_id": None,
                                           "created_at": now_iso()} for n in names])
    s = await db.settings.find_one({"key": "general"})
    if not s:
        await db.settings.insert_one({"key": "general", "rating_scale": 5, "stale_days": 7, "offer_expiry_alert_days": 3,
                                      "transitions": default_transitions()})
    email = os.environ["ADMIN_EMAIL"].lower()
    if not await db.users.find_one({"email": email}):
        await db.users.insert_one({"id": new_id(), "email": email, "name": os.environ.get("ADMIN_NAME", "Super Admin"),
                                   "role": "super_admin", "active": True, "password_hash": hash_password(os.environ["ADMIN_PASSWORD"]),
                                   "must_change_password": False, "created_at": now_iso()})


async def scan_alerts():
    t = today()
    soon = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
    async for iv in db.interviews.find({"status": {"$in": ["Scheduled", "Rescheduled"]}}, {"_id": 0}):
        targets = []
        for i in iv.get("interviewer_ids", []):
            targets += await user_ids_for_person(i)
        if iv.get("date") and t <= iv["date"] <= soon:
            await notify(targets + await user_ids_for_person((await db.applications.find_one({"id": iv["application_id"]}) or {}).get("recruiter_id")),
                         "interview", "Upcoming interview", f"{iv['code']} · {iv['round_name']} on {iv['date']} {iv.get('start_time') or ''}",
                         "/interviews", key=f"upcoming:{iv['id']}:{iv['date']}")
        if iv.get("date") and iv["date"] < t and iv.get("feedback_status") != "Complete":
            await notify(targets, "feedback", "Interview feedback pending", f"{iv['code']} · {iv['round_name']} on {iv['date']}",
                         "/interviews", key=f"feedback:{iv['id']}:{t}")
    s = await db.settings.find_one({"key": "general"}) or {}
    exp_days = s.get("offer_expiry_alert_days", 3)
    horizon = (datetime.now(timezone.utc) + timedelta(days=exp_days)).date().isoformat()
    admins = await admin_user_ids()
    async for o in db.offers.find({"status": "Released"}, {"_id": 0}):
        v = o.get("validity_date")
        if v and v < t:
            await db.offers.update_one({"id": o["id"]}, {"$set": {"status": "Expired"}, "$push": {"history": {"at": now_iso(), "by": "System", "action": "Expired", "details": v}}})
            await notify(admins + await user_ids_for_person(o.get("recruiter_id")), "offer", "Offer expired", f"{o['code']} expired on {v}", "/offers", key=f"expired:{o['id']}")
        elif v and v <= horizon:
            await notify(admins + await user_ids_for_person(o.get("recruiter_id")), "offer", "Offer expiring soon", f"{o['code']} valid until {v}", "/offers", key=f"expiring:{o['id']}")
    async for o in db.offers.find({"status": "Approval Pending"}, {"_id": 0}):
        await notify(admins, "offer", "Offer approval pending", f"{o['code']} · ₹{o.get('ctc')} L", "/offers", key=f"approval:{o['id']}:{t}")
    week = (datetime.now(timezone.utc) + timedelta(days=7)).date().isoformat()
    async for j in db.joinings.find({"status": {"$in": ["Pending", "Joining Confirmed", "Joining Deferred"]}}, {"_id": 0}):
        d = j.get("confirmed_date") or j.get("tentative_date")
        if d and t <= d <= week:
            await notify(admins + await user_ids_for_person(j.get("recruiter_id")), "joining", "Upcoming joining", f"{j['code']} expected on {d}", "/joining", key=f"join:{j['id']}:{d}")
        if j["status"] == "Pending" and not j.get("confirmed_date") and d and d <= week:
            await notify(await user_ids_for_person(j.get("recruiter_id")), "followup", "Candidate follow-up needed", f"Confirm joining for {j['code']}", "/joining", key=f"follow:{j['id']}:{t}")
    stale = s.get("stale_days", 7)
    async for a in db.applications.find({"closed": False}, {"_id": 0, "history": 0}):
        if days_between(a["stage_entered_at"][:10], t) > stale:
            await notify(await user_ids_for_person(a.get("recruiter_id")), "stale", "Candidate stuck in stage",
                         f"{a['code']} has been in '{a['status']}' for over {stale} days", f"/candidates/{a['candidate_id']}",
                         key=f"stale:{a['id']}:{a['stage_entered_at'][:10]}")


async def alert_loop():
    while True:
        try:
            await scan_alerts()
        except Exception as exc:
            logger.error("alert scan failed: %s", exc)
        await asyncio.sleep(1800)


app = FastAPI(title="MMS Recruitment Portal")
for r in (routes_admin, routes_recruit, routes_interviews, routes_offers, routes_analytics, routes_import):
    app.include_router(r.router)


@app.get("/api/health")
async def health():
    return {"ok": True}


app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=os.environ["CORS_ORIGINS"].split(","),
                   allow_methods=["*"], allow_headers=["*"], expose_headers=["Content-Disposition"])


@app.on_event("startup")
async def startup():
    await seed()
    try:
        await asyncio.to_thread(init_storage)
    except Exception as exc:
        logger.error("storage init failed: %s", exc)
    app.state.alerts = asyncio.create_task(alert_loop())


@app.on_event("shutdown")
async def shutdown():
    app.state.alerts.cancel()
    with suppress(asyncio.CancelledError):
        await app.state.alerts
    client.close()
