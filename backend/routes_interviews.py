import re
from typing import Optional, List, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core import (db, get_user, require, can, now_iso, today, new_id, next_code, log_activity, notify, get_scope,
                  get_visible, masters_map, user_ids_for_person, person_ids, set_app_status, get_settings,
                  RECOMMENDATIONS, INTERVIEW_MODES, PIPELINE)

router = APIRouter(prefix="/api")
OPEN_IV = ["Scheduled", "Rescheduled"]


async def sync_interview_stage(app, user, note, records=()):
    """Keep the application stage in step with its interviews: Interview Completed only when the requisition's
    required rounds are complete with all feedback; otherwise Interview In Progress."""
    from workflow import evaluate
    app = await db.applications.find_one({"id": app["id"]}, {"_id": 0})
    if app["status"] not in ("Interview Scheduled", "Interview In Progress"):
        return app
    steps = await evaluate(app, "Interview Completed")
    done = all(s["done"] for s in steps if s["blocking"])
    return await set_app_status(app, "Interview Completed" if done else "Interview In Progress", user, auto=True, note=note, records=list(records))
RATING_KEYS = ["technical", "communication", "problem_solving", "relevant_experience", "role_fit", "overall"]


class InterviewIn(BaseModel):
    application_id: Optional[str] = None
    round_name: Optional[str] = None
    round_type_id: Optional[str] = None
    date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    mode: Optional[str] = None
    interviewer_ids: Optional[List[str]] = None
    location: Optional[str] = None
    remarks: Optional[str] = None
    force: Optional[bool] = False


async def conflicts(ids, d, start, end, exclude=None):
    if not (d and start and end):
        return []
    q = {"date": d, "status": {"$in": OPEN_IV}, "interviewer_ids": {"$in": ids}}
    if exclude:
        q["id"] = {"$ne": exclude}
    mm = await masters_map()
    out = []
    async for iv in db.interviews.find(q, {"_id": 0}):
        if iv.get("start_time") and iv.get("end_time") and iv["start_time"] < end and start < iv["end_time"]:
            names = [mm.get(i) for i in set(ids) & set(iv["interviewer_ids"])]
            out.append(f"{', '.join(n for n in names if n)} already has {iv['code']} at {iv['start_time']}–{iv['end_time']}")
    return out


def validate_slot(data):
    if data.get("start_time") and data.get("end_time") and data["start_time"] >= data["end_time"]:
        raise HTTPException(400, "End time must be after start time")
    if data.get("mode") and data["mode"] not in INTERVIEW_MODES:
        raise HTTPException(400, "Invalid interview mode")


async def enrich_ivs(ivs, user):
    mm = await masters_map()
    mine = set(await person_ids(user, "interviewer"))
    cids = {i["candidate_id"] for i in ivs}
    rids = {i["requisition_id"] for i in ivs}
    cands = {c["id"]: c["name"] async for c in db.candidates.find({"id": {"$in": list(cids)}}, {"id": 1, "name": 1})}
    reqs = {r["id"]: r async for r in db.requisitions.find({"id": {"$in": list(rids)}}, {"_id": 0, "id": 1, "title": 1, "code": 1, "department_id": 1})}
    fb = {}
    async for f in db.feedback.find({"interview_id": {"$in": [i["id"] for i in ivs]}}, {"interview_id": 1, "interviewer_id": 1}):
        fb.setdefault(f["interview_id"], set()).add(f["interviewer_id"])
    for i in ivs:
        r = reqs.get(i["requisition_id"], {})
        done = fb.get(i["id"], set())
        i.update({"candidate_name": cands.get(i["candidate_id"]), "requisition_title": r.get("title"),
                  "requisition_code": r.get("code"), "department": mm.get(r.get("department_id")),
                  "round_type": mm.get(i.get("round_type_id")),
                  "interviewers": [mm.get(x) for x in i.get("interviewer_ids", [])],
                  "feedback_count": len(done), "my_pending": list((mine & set(i.get("interviewer_ids", []))) - done),
                  "feedback_pending": [x for x in i.get("interviewer_ids", []) if x not in done]})
    return ivs


async def list_interviews(user, f):
    scope = await get_scope(user)
    q = dict(scope.q("interview"))
    for k in ("status", "requisition_id", "candidate_id", "application_id", "feedback_status"):
        if f.get(k):
            q[k] = f[k]
    if f.get("interviewer_id"):
        # combine with (never replace) the interviewer's own scope filter
        q = {"$and": [q, {"interviewer_ids": f["interviewer_id"]}]}
    if f.get("date_from") or f.get("date_to"):
        q["date"] = {k: v for k, v in (("$gte", f.get("date_from")), ("$lte", f.get("date_to"))) if v}
    ivs = await db.interviews.find(q, {"_id": 0}).sort([("date", -1), ("start_time", -1)]).to_list(5000)
    ivs = await enrich_ivs(ivs, user)
    if f.get("mine") == "true":
        mine = set(await person_ids(user, "interviewer"))
        ivs = [i for i in ivs if mine & set(i["interviewer_ids"])]
    return ivs


@router.get("/interviews")
async def get_interviews(request: Request, user=Depends(require("interview.view"))):
    return await list_interviews(user, dict(request.query_params))


@router.post("/interviews")
async def schedule_interview(body: InterviewIn, user=Depends(require("interview.manage"))):
    data = body.model_dump()
    force = data.pop("force")
    app = await get_visible("applications", "app", data.get("application_id") or "", await get_scope(user))
    if app["closed"] and app["status"] != "On Hold":
        raise HTTPException(400, f"Application is {app['status']} — interviews cannot be scheduled")
    if app["status"] in PIPELINE[PIPELINE.index("Selected"):]:
        raise HTTPException(400, f"Candidate is already {app['status']} — no further interviews can be scheduled")
    if not data.get("date") or not data.get("interviewer_ids") or not data.get("round_name"):
        raise HTTPException(400, "Round name, date and at least one interviewer are required")
    from workflow import assert_prerequisites
    await assert_prerequisites(app, "Interview Scheduled", keys={"screening", "shortlisting"})
    validate_slot(data)
    clash = await conflicts(data["interviewer_ids"], data["date"], data.get("start_time"), data.get("end_time"))
    if clash and not force:
        raise HTTPException(409, {"message": "Interviewer schedule conflict", "conflicts": clash})
    n = await db.interviews.count_documents({"application_id": app["id"], "status": {"$ne": "Cancelled"}})
    ts = now_iso()
    doc = data | {"id": new_id(), "code": await next_code("INT"), "candidate_id": app["candidate_id"],
                  "requisition_id": app["requisition_id"], "round_number": n + 1, "status": "Scheduled",
                  "feedback_status": "Pending", "outcome": "Pending", "created_by": user["id"], "created_at": ts,
                  "updated_at": ts, "history": [{"at": ts, "by": user["name"], "action": "Scheduled",
                                                 "details": f"{data['date']} {data.get('start_time') or ''}"}]}
    await db.interviews.insert_one(doc)
    doc.pop("_id", None)
    cand = await db.candidates.find_one({"id": app["candidate_id"]}, {"name": 1})
    await log_activity(user, "interview_schedule", "application", app["id"], f"{cand['name']} · {doc['code']}",
                       f"Round {doc['round_number']} {doc['round_name']} on {doc['date']}" + (" (conflict overridden)" if clash else ""))
    if app["status"] in ("New", "Screening", "Shortlisted", "Interview Completed", "On Hold"):
        await set_app_status(app, "Interview Scheduled", user, auto=True, note=doc["code"], records=[doc["id"]])
    targets = []
    for i in data["interviewer_ids"]:
        targets += await user_ids_for_person(i)
    await notify(targets, "interview", "Interview assigned to you",
                 f"{cand['name']} · {doc['round_name']} on {doc['date']} {doc.get('start_time') or ''}", "/interviews")
    return doc


@router.get("/interviews/{iid}")
async def get_interview(iid: str, user=Depends(require("interview.view"))):
    iv = (await enrich_ivs([await get_visible("interviews", "interview", iid, await get_scope(user))], user))[0]
    q = {"interview_id": iid}
    if not can(user, "feedback.view"):
        q["interviewer_id"] = {"$in": await person_ids(user, "interviewer")}
    iv["feedback"] = await db.feedback.find(q, {"_id": 0}).to_list(50)
    mm = await masters_map()
    for f in iv["feedback"]:
        f["interviewer"] = mm.get(f["interviewer_id"])
    return iv


@router.put("/interviews/{iid}")
async def update_interview(iid: str, body: InterviewIn, user=Depends(require("interview.manage"))):
    iv = await get_visible("interviews", "interview", iid, await get_scope(user))
    data = {k: v for k, v in body.model_dump(exclude_unset=True).items() if k in ("round_name", "round_type_id", "mode", "location", "remarks", "interviewer_ids")}
    validate_slot(data)
    if data.get("interviewer_ids") and not body.force:
        clash = await conflicts(data["interviewer_ids"], iv["date"], iv.get("start_time"), iv.get("end_time"), iid)
        if clash:
            raise HTTPException(409, {"message": "Interviewer schedule conflict", "conflicts": clash})
    data["updated_at"] = now_iso()
    await db.interviews.update_one({"id": iid}, {"$set": data, "$push": {"history": {"at": now_iso(), "by": user["name"], "action": "Updated", "details": ", ".join(data)}}})
    await log_activity(user, "interview_update", "application", iv["application_id"], iv["code"], ", ".join(data))
    return await get_interview(iid, user)


class RescheduleIn(BaseModel):
    date: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    reason: str
    force: Optional[bool] = False


@router.post("/interviews/{iid}/reschedule")
async def reschedule(iid: str, body: RescheduleIn, user=Depends(require("interview.manage"))):
    iv = await get_visible("interviews", "interview", iid, await get_scope(user))
    if iv["status"] not in OPEN_IV:
        raise HTTPException(400, f"A {iv['status']} interview cannot be rescheduled")
    if not body.reason.strip():
        raise HTTPException(400, "Reason is required")
    validate_slot(body.model_dump())
    clash = await conflicts(iv["interviewer_ids"], body.date, body.start_time, body.end_time, iid)
    if clash and not body.force:
        raise HTTPException(409, {"message": "Interviewer schedule conflict", "conflicts": clash})
    details = f"{iv['date']} {iv.get('start_time') or ''} → {body.date} {body.start_time or ''} ({body.reason})"
    await db.interviews.update_one({"id": iid}, {"$set": {"date": body.date, "start_time": body.start_time, "end_time": body.end_time,
                                                          "status": "Rescheduled", "updated_at": now_iso()},
                                                 "$push": {"history": {"at": now_iso(), "by": user["name"], "action": "Rescheduled", "details": details}}})
    await log_activity(user, "interview_reschedule", "application", iv["application_id"], iv["code"], details)
    targets = []
    for i in iv["interviewer_ids"]:
        targets += await user_ids_for_person(i)
    await notify(targets, "interview", "Interview rescheduled", f"{iv['code']} · {details}", "/interviews")
    return await get_interview(iid, user)


class IvStatusIn(BaseModel):
    status: Optional[str] = None
    outcome: Optional[str] = None
    reason: Optional[str] = None
    override_reason: Optional[str] = None  # Super Admin: complete without all feedback (audited)


@router.post("/interviews/{iid}/status")
async def interview_status(iid: str, body: IvStatusIn, user=Depends(get_user)):
    if not (can(user, "interview.manage") or (can(user, "selection.decide") and not body.status)):
        raise HTTPException(403, "Not permitted")
    iv = await get_visible("interviews", "interview", iid, await get_scope(user))
    upd = {"updated_at": now_iso()}
    if body.status:
        if body.status not in ("Completed", "Cancelled", "No Show"):
            raise HTTPException(400, "Invalid status")
        if body.status in ("Cancelled", "No Show") and not (body.reason or "").strip():
            raise HTTPException(400, "Reason is required")
        if iv["status"] in ("Cancelled", "Completed", "No Show") and body.status != iv["status"]:
            raise HTTPException(400, f"Interview is already {iv['status']}")
        if body.status == "Completed" and iv["status"] != "Completed":
            given = {f["interviewer_id"] async for f in db.feedback.find({"interview_id": iid}, {"interviewer_id": 1})}
            missing = [i for i in iv.get("interviewer_ids", []) if i not in given]
            if missing:
                from workflow import is_override_user
                if not (body.override_reason or "").strip():
                    mm = await masters_map()
                    raise HTTPException(400, f"Feedback is missing from {', '.join(mm.get(i) or i for i in missing)} — submit it before completing the interview")
                if not is_override_user(user):
                    raise HTTPException(403, "Only a Super Admin can complete an interview without all feedback")
                upd["feedback_override"] = {"reason": body.override_reason.strip(), "by": user["name"], "at": now_iso(), "missing": missing}
        upd["status"] = body.status
    if body.outcome:
        if body.outcome not in ("Pending", "Selected", "Rejected", "On Hold"):
            raise HTTPException(400, "Invalid outcome")
        upd["outcome"] = body.outcome
    if body.outcome and body.outcome != "Pending" and (body.status or iv["status"]) != "Completed":
        raise HTTPException(400, "Record the final recommendation once the interview is completed")
    action = " / ".join(x for x in (body.status, body.outcome and f"Outcome {body.outcome}") if x)
    if upd.get("feedback_override"):
        action += f" [EXCEPTION: completed without all feedback — {body.override_reason}]"
    await db.interviews.update_one({"id": iid}, {"$set": upd, "$push": {"history": {"at": now_iso(), "by": user["name"], "action": action, "details": body.reason or ""}}})
    await log_activity(user, "interview_status", "application", iv["application_id"], iv["code"], action + (f" ({body.reason})" if body.reason else ""))
    app = await db.applications.find_one({"id": iv["application_id"]}, {"_id": 0})
    if body.status == "Completed" or body.outcome:
        await sync_interview_stage(app, user, iv["code"], [iid])
    if body.status == "No Show" and app["status"] in ("Interview Scheduled", "Interview In Progress"):
        await set_app_status(app, "No Show", user, reason=body.reason, auto=True, note=iv["code"])
    return await get_interview(iid, user)


class FeedbackIn(BaseModel):
    interviewer_id: Optional[str] = None
    ratings: Dict[str, int]
    recommendation: str
    detailed: str
    strengths: Optional[str] = ""
    improvements: Optional[str] = ""


@router.post("/interviews/{iid}/feedback")
async def submit_feedback(iid: str, body: FeedbackIn, user=Depends(require("feedback.submit"))):
    iv = await get_visible("interviews", "interview", iid, await get_scope(user))
    mine = set(await person_ids(user, "interviewer")) & set(iv["interviewer_ids"])
    if body.interviewer_id and user["role"] in ("super_admin", "recruiter"):
        if body.interviewer_id not in iv["interviewer_ids"]:
            raise HTTPException(400, "Interviewer is not assigned to this interview")
        ivr = body.interviewer_id
    elif mine:
        ivr = sorted(mine)[0]
    else:
        raise HTTPException(403, "You can only submit feedback for interviews assigned to you")
    if iv["status"] in ("Cancelled", "No Show"):
        raise HTTPException(400, f"Feedback cannot be submitted for a {iv['status']} interview")
    scale = (await get_settings()).get("rating_scale", 5)
    for k in RATING_KEYS:
        v = body.ratings.get(k)
        if v is None or not 1 <= v <= scale:
            raise HTTPException(400, f"Rating '{k.replace('_', ' ')}' must be between 1 and {scale}")
    if body.recommendation not in RECOMMENDATIONS or not body.detailed.strip():
        raise HTTPException(400, "Recommendation and detailed feedback are required")
    doc = {"interview_id": iid, "interviewer_id": ivr, "application_id": iv["application_id"], "candidate_id": iv["candidate_id"],
           "ratings": {k: body.ratings[k] for k in RATING_KEYS}, "scale": scale, "recommendation": body.recommendation,
           "detailed": body.detailed, "strengths": body.strengths, "improvements": body.improvements,
           "submitted_by": user["name"], "submitted_at": now_iso()}
    if await db.feedback.find_one({"interview_id": iid, "interviewer_id": ivr}):
        mm = await masters_map()
        raise HTTPException(409, f"Feedback from {mm.get(ivr) or 'this interviewer'} has already been submitted for {iv['code']}")
    await db.feedback.insert_one(doc | {"id": new_id()})
    count = await db.feedback.count_documents({"interview_id": iid})
    total = len(iv["interviewer_ids"])
    upd = {"feedback_status": "Complete" if count >= total else "Partial", "updated_at": now_iso()}
    if count >= total and iv["status"] in OPEN_IV:
        upd["status"] = "Completed"
    await db.interviews.update_one({"id": iid}, {"$set": upd})
    mm = await masters_map()
    await log_activity(user, "feedback_submit", "application", iv["application_id"], iv["code"],
                       f"{mm.get(ivr)}: {body.recommendation} (overall {body.ratings['overall']}/{scale})")
    app = await db.applications.find_one({"id": iv["application_id"]}, {"_id": 0})
    await sync_interview_stage(app, user, iv["code"], [iid])
    await notify(await user_ids_for_person(app.get("recruiter_id")), "feedback", "Interview feedback submitted",
                 f"{iv['code']} · {mm.get(ivr)}: {body.recommendation}", f"/candidates/{iv['candidate_id']}")
    return await get_interview(iid, user)
