"""Executive dashboard — one aggregated, role-scoped payload built from real records.

Every figure comes from applications (and their stage history), requisitions, interviews, feedback, offers,
joinings and confirmed hire costs that the signed-in user is allowed to see. Nothing is estimated: when a
comparison period has no data the change is returned as null and the UI shows "—".
"""
from collections import defaultdict
from datetime import date, timedelta
from statistics import median

from fastapi import APIRouter, Depends, HTTPException, Request

from core import db, require, can, get_scope, today, days_between, INACTIVE, PIPELINE
from routes_recruit import list_applications, list_requisitions
from routes_interviews import list_interviews
from routes_analytics import compute, stage_idx, pct

router = APIRouter(prefix="/api")

PERIODS = ("7d", "30d", "90d", "quarter", "year", "custom")
INTERVIEW_STAGES = ["Interview Scheduled", "Interview In Progress", "Interview Completed"]
FUNNEL = [("New", 0, ["New"]), ("Screening", 1, ["Screening"]), ("Shortlisted", 2, ["Shortlisted"]),
          ("Interview", 3, INTERVIEW_STAGES), ("Selected", 6, ["Selected"]), ("Offer Released", 8, ["Offer Approval Pending", "Offer Released"]),
          ("Offer Accepted", 9, ["Offer Accepted"]), ("Joined", 10, ["Joined"])]
ACTIVITY = {"New": "Candidate added", "Shortlisted": "Candidate shortlisted", "Interview Scheduled": "Interview scheduled",
            "Selected": "Candidate selected", "Offer Released": "Offer released", "Offer Accepted": "Offer accepted", "Joined": "Candidate joined"}


def d(s):
    return date.fromisoformat(s[:10])


def period_bounds(f):
    t = date.fromisoformat(today())
    p = f.get("period") or "30d"
    if p not in PERIODS:
        raise HTTPException(400, "Unknown period")
    if p == "custom":
        if not f.get("date_from") or not f.get("date_to"):
            raise HTTPException(400, "Choose a start and end date")
        start, end = d(f["date_from"]), d(f["date_to"])
        if start > end:
            raise HTTPException(400, "Start date must be before end date")
    elif p == "quarter":
        start, end = date(t.year, 3 * ((t.month - 1) // 3) + 1, 1), t
    elif p == "year":
        start, end = date(t.year, 1, 1), t
    else:
        start, end = t - timedelta(days=int(p[:-1]) - 1), t
    length = (end - start).days + 1
    pend = start - timedelta(days=1)
    return p, start, end, pend - timedelta(days=length - 1), pend


def bucket_key(x, gran):
    if gran == "week":
        return (x - timedelta(days=x.weekday())).isoformat()
    return x.isoformat()[:7]


def buckets(start, end, gran):
    out, x = [], start
    while x <= end:
        k = bucket_key(x, gran)
        if k not in out:
            out.append(k)
        x += timedelta(days=1)
    return out


def change(cur, prev):
    return round((cur - prev) * 100 / prev, 1) if prev else None


def first_entry(a, status):
    for h in a.get("history") or []:
        if h.get("status") == status and h.get("at"):
            return h["at"][:10]
    return None


@router.get("/dashboard")
async def dashboard(request: Request, user=Depends(require("analytics.view"))):
    f = dict(request.query_params)
    period, start, end, pstart, pend = period_bounds(f)
    gran = f.get("granularity") or ("week" if (end - start).days <= 92 else "month")
    if gran not in ("week", "month"):
        raise HTTPException(400, "Granularity must be week or month")
    within = lambda s, a=start, b=end: bool(s) and a <= d(s) <= b
    scope_f = {k: f.get(k) for k in ("department_id", "recruiter_id", "requisition_id") if f.get(k)}

    # ---------- base records (role-scoped) ----------
    apps = await list_applications(user, {k: v for k, v in scope_f.items() if k != "department_id"})
    if f.get("department_id"):
        apps = [a for a in apps if a.get("department_id") == f["department_id"]]
    app_ids = [a["id"] for a in apps]
    amap = {a["id"]: a for a in apps}
    joins = {j["application_id"]: j async for j in db.joinings.find({"application_id": {"$in": app_ids}, "status": "Joined"}, {"_id": 0})}
    offers = [o async for o in db.offers.find({"application_id": {"$in": app_ids}}, {"_id": 0, "history": 0})] if can(user, "offer.view") else []
    ivs_all = [i async for i in db.interviews.find({"application_id": {"$in": app_ids}}, {"_id": 0, "history": 0})]
    for a in apps:
        a["_idx"] = stage_idx(a)
        a["_join"] = (joins.get(a["id"]) or {}).get("actual_date") if a["status"] == "Joined" else None
    reqs = await list_requisitions(user, {k: f.get(k) for k in ("department_id", "recruiter_id") if f.get(k)})
    if f.get("requisition_id"):
        reqs = [r for r in reqs if r["id"] == f["requisition_id"]]

    # ---------- events ----------
    def events(kind):
        if kind == "added":
            first = {}
            for a in apps:
                c = a["created_at"][:10]
                first[a["candidate_id"]] = min(first.get(a["candidate_id"], c), c)
            return list(first.values())
        if kind == "screening":
            return [x for x in (first_entry(a, "Screening") for a in apps) if x]
        if kind == "shortlisted":
            return [x for x in (first_entry(a, "Shortlisted") for a in apps) if x]
        if kind == "interview":
            return [x for x in (first_entry(a, "Interview Scheduled") for a in apps) if x]
        if kind == "interviews_completed":
            return [i["date"] for i in ivs_all if i.get("status") == "Completed" and i.get("date")]
        if kind in ("offers_released", "offers_accepted"):
            # one event per application (its first release / acceptance) — re-offers do not double count
            field = "release_date" if kind == "offers_released" else "accepted_date"
            first = {}
            for o in offers:
                if o.get(field) and (kind == "offers_released" or o.get("status") == "Accepted"):
                    first[o["application_id"]] = min(first.get(o["application_id"], o[field]), o[field])
            return list(first.values())
        if kind == "joined":
            return [a["_join"] for a in apps if a["_join"]]
        if kind == "reqs_opened":
            return [r["created_at"][:10] for r in reqs if r.get("created_at")]
        return []

    def flow(kind):
        ev = events(kind)
        cur = sum(1 for x in ev if within(x))
        prev = sum(1 for x in ev if within(x, pstart, pend))
        return cur, prev, len(ev)

    def kpi(key, label, value, kind, note, link, flow_is_value=False):
        cur, prev, total = flow(kind)
        return {"key": key, "label": label, "value": cur if flow_is_value else value, "period_count": cur, "previous_count": prev,
                "change_pct": change(cur, prev), "all_time": total, "note": note, "link": link, "flow": flow_is_value}

    by_status = defaultdict(int)
    for a in apps:
        by_status[a["status"]] += 1
    open_reqs = [r for r in reqs if r.get("status") == "Open"]
    hero = [
        kpi("candidates", "Total candidates", len({a["candidate_id"] for a in apps}), "added", "new in period", "/candidates"),
        kpi("open_requisitions", "Open requisitions", len(open_reqs), "reqs_opened", "raised in period", "/requisitions?status=Open"),
        kpi("hires", "Hires", by_status["Joined"], "joined", "joined in period", "/pipeline?status=Joined", flow_is_value=True),
        kpi("screening", "In screening", by_status["Screening"], "screening", "entered in period", "/pipeline?status=Screening"),
        kpi("interview", "In interview", sum(by_status[s] for s in INTERVIEW_STAGES), "interview", "entered in period", "/pipeline?status=" + ",".join(INTERVIEW_STAGES)),
    ]
    if can(user, "offer.view"):
        hero += [kpi("offers_released", "Offers released", None, "offers_released", "released in period", "/offers?status=Released", flow_is_value=True),
                 kpi("offers_accepted", "Offers accepted", None, "offers_accepted", "accepted in period", "/offers?status=Accepted", flow_is_value=True)]

    # ---------- trend series ----------
    keys = buckets(start, end, gran)
    series_kinds = [("added", "Candidates added"), ("shortlisted", "Shortlisted"), ("interviews_completed", "Interviews completed")]
    if can(user, "offer.view"):
        series_kinds.append(("offers_released", "Offers released"))
    series_kinds.append(("joined", "Joined"))
    trend = [{"bucket": k} | {kind: 0 for kind, _ in series_kinds} for k in keys]
    idx = {k: i for i, k in enumerate(keys)}
    for kind, _ in series_kinds:
        for x in events(kind):
            if within(x):
                trend[idx[bucket_key(d(x), gran)]][kind] += 1

    # ---------- funnel (applications created in the period) ----------
    cohort = [a for a in apps if within(a["created_at"])]
    funnel, prev_n = [], None
    for label, i, statuses in FUNNEL:
        n = sum(1 for a in cohort if a["status"] == "Joined") if label == "Joined" else sum(1 for a in cohort if a["_idx"] >= i)
        funnel.append({"stage": label, "count": n, "conversion": pct(n, prev_n) if prev_n is not None else None,
                       "drop_off": (prev_n - n) if prev_n is not None else None, "statuses": statuses})
        prev_n = n
    overall = pct(funnel[-1]["count"], funnel[0]["count"])

    # ---------- analytics module (same calculations as the Analytics page & exports) ----------
    an = await compute(user, {**scope_f, "date_from": start.isoformat(), "date_to": end.isoformat()})
    cost = None
    if an.get("cost"):
        c = an["cost"]
        ct = {k: [] for k in keys}
        for h in c["hire_costs"]:
            if h.get("total") is not None and h.get("joined_on") and within(h["joined_on"]):
                ct[bucket_key(d(h["joined_on"]), gran)].append(h["total"])
        cost = {k: c[k] for k in ("formula", "total", "ctc_total", "consulting_total", "recruiter_total", "fees", "hires", "joined", "unconfirmed", "cost_per_hire")}
        cost["trend"] = [{"bucket": k, "avg": round(sum(v) / len(v), 2) if v else None, "hires": len(v)} for k, v in ct.items()]
        cost["pending_confirmation"] = sum(1 for a in apps if a["status"] == "Offer Accepted" and not a.get("hire_cost"))
    aph = an["aph"]
    by_req = defaultdict(list)
    for h in aph["hires"]:
        if h.get("days") is not None:
            by_req[(h.get("requisition_code"), h.get("role"))].append(h["days"])
    aph_trend = {k: [] for k in keys}
    for h in aph["hires"]:
        if h.get("days") is not None and h.get("joined_on") and within(h["joined_on"]):
            aph_trend[bucket_key(d(h["joined_on"]), gran)].append(h["days"])
    age = {"completed": aph["completed"], "flagged": aph["flagged"], "missing_crf": aph["incomplete_requisitions"],
           "trend": [{"bucket": k, "avg": round(sum(v) / len(v), 1) if v else None, "hires": len(v)} for k, v in aph_trend.items()],
           "by_requisition": sorted([{"requisition": c or "—", "role": r, "avg": round(sum(v) / len(v), 1), "hires": len(v), "max": max(v)} for (c, r), v in by_req.items()],
                                    key=lambda x: -x["avg"])[:8]}

    source_ids = {m["name"]: m["id"] async for m in db.masters.find({"type": "source"}, {"id": 1, "name": 1})}
    sources = sorted([{"source": s["source"], "source_id": source_ids.get(s["source"]), "candidates": s["total"], "shortlisted": s["shortlisted"],
                       "interviewed": s["interviewed"], "joined": s["joined"], "conversion": s["conversion"]} for s in an["sources"]], key=lambda x: -x["candidates"])

    aph_by_rec = {x["name"]: x for x in aph["by_recruiter"]}
    iv_by_rec = defaultdict(int)
    for i in ivs_all:
        a = amap.get(i["application_id"])
        if a and within(i.get("date")):
            iv_by_rec[a.get("recruiter_id")] += 1
    recruiters = sorted([{"recruiter_id": r["recruiter_id"], "name": r["name"], "assigned": r["total"], "screened": r["screened"],
                          "interviews": iv_by_rec.get(r["recruiter_id"], 0), "offers_released": r["offers_released"], "joined": r["joined"],
                          "avg_age_per_hire": (aph_by_rec.get(r["name"]) or {}).get("avg"), "cost_per_hire": r.get("cost_per_hire") if cost else None}
                         for r in an["recruiters"]], key=lambda x: -x["assigned"])

    # ---------- requisition health (own filters) ----------
    rq = reqs
    for k in ("hiring_manager_id", "location_id"):
        if f.get(k):
            rq = [r for r in rq if r.get(k) == f[k]]
    if f.get("req_status"):
        rq = [r for r in rq if r.get("status") == f["req_status"]]
    filled_days = []
    for r in rq:
        if r.get("crf_date") and (r.get("positions") or 0) and (r.get("filled_positions") or 0) >= r["positions"]:
            dates = [a["_join"] for a in apps if a["requisition_id"] == r["id"] and a["_join"]]
            if dates:
                filled_days.append(days_between(r["crf_date"], max(dates)))
    ageing_buckets = {"0–30 days": 0, "31–60 days": 0, "61–90 days": 0, "90+ days": 0, "No CRF date": 0}
    for r in rq:
        if r.get("status") != "Open":
            continue
        h = r.get("current_hiring_age")
        key = "No CRF date" if h is None else "0–30 days" if h <= 30 else "31–60 days" if h <= 60 else "61–90 days" if h <= 90 else "90+ days"
        ageing_buckets[key] += 1
    requisitions = {"open": sum(1 for r in rq if r.get("status") == "Open"), "on_hold": sum(1 for r in rq if r.get("status") == "On Hold"),
                    "positions": sum(r.get("positions") or 0 for r in rq), "filled": sum(r.get("filled_positions") or 0 for r in rq),
                    "remaining": sum(r["open_positions"] for r in rq if r.get("status") in ("Open", "On Hold")),
                    "avg_time_to_fill": round(sum(filled_days) / len(filled_days), 1) if filled_days else None, "time_to_fill_count": len(filled_days),
                    "ageing": [{"bucket": k, "count": v} for k, v in ageing_buckets.items()],
                    "oldest": sorted([{"id": r["id"], "code": r["code"], "title": r["title"], "status": r["status"], "department": r.get("department"),
                                       "hiring_manager": r.get("hiring_manager"), "location": r.get("location"), "age": r.get("current_hiring_age"),
                                       "filled": r.get("filled_positions") or 0, "positions": r.get("positions") or 0}
                                      for r in rq if r.get("status") in ("Open", "On Hold")], key=lambda x: -(x["age"] or -1))[:6]}

    # ---------- operations ----------
    t = today()
    my = await list_interviews(user, {"date_from": t})  # the user's own interview scope
    upcoming = sorted([i for i in my if i.get("status") in ("Scheduled", "Rescheduled") and i["application_id"] in amap],
                      key=lambda i: (i.get("date") or "", i.get("start_time") or ""))
    upcoming = [{"id": i["id"], "date": i["date"], "time": i.get("start_time"), "candidate": i.get("candidate_name"), "candidate_id": i["candidate_id"],
                 "requisition": i.get("requisition_title"), "round": f"Round {i.get('round_number')} · {i.get('round_name')}",
                 "interviewers": [x for x in i.get("interviewers", []) if x], "status": i["status"], "today": i["date"] == t} for i in upcoming[:8]]

    feed = []
    for a in apps:
        for h in a.get("history") or []:
            label = ACTIVITY.get(h.get("status"))
            if label and h.get("at") and not h.get("migration_id"):
                feed.append({"at": h["at"], "event": label, "candidate": a.get("candidate_name"), "candidate_id": a["candidate_id"],
                             "requisition": a.get("requisition_title"), "by": h.get("by") or "System"})
    async for fb in db.feedback.find({"application_id": {"$in": app_ids}}, {"_id": 0, "application_id": 1, "submitted_at": 1, "submitted_by": 1}):
        a = amap.get(fb["application_id"])
        feed.append({"at": fb.get("submitted_at"), "event": "Interview feedback submitted", "candidate": a.get("candidate_name"),
                     "candidate_id": a["candidate_id"], "requisition": a.get("requisition_title"), "by": fb.get("submitted_by")})
    feed = sorted([x for x in feed if x["at"]], key=lambda x: x["at"], reverse=True)[:14]

    scope = await get_scope(user)
    pending = []
    fb_q = {"status": {"$in": ["Scheduled", "Rescheduled", "Completed"]}, "date": {"$lte": t}, "feedback_status": {"$ne": "Complete"},
            "feedback_override": {"$exists": False}, **scope.q("interview")}
    fb_pending = [i async for i in db.interviews.find(fb_q, {"_id": 0, "application_id": 1}) if i["application_id"] in amap]
    pending.append({"key": "feedback", "label": "Interview feedback pending", "count": len(fb_pending), "link": "/interviews?feedback_status=Pending"})
    if can(user, "interview.manage") or can(user, "app.view"):
        live = {i["application_id"] for i in ivs_all if i.get("status") in ("Scheduled", "Rescheduled")}
        n = sum(1 for a in apps if a["status"] == "Shortlisted" and a["id"] not in live)
        pending.append({"key": "to_schedule", "label": "Shortlisted, awaiting interview scheduling", "count": n, "link": "/pipeline?status=Shortlisted"})
    if can(user, "offer.view"):
        pending.append({"key": "approval", "label": "Offers awaiting approval", "count": sum(1 for o in offers if o["status"] == "Approval Pending"), "link": "/offers?status=Approval Pending"})
        pending.append({"key": "acceptance", "label": "Offers awaiting candidate response", "count": sum(1 for o in offers if o["status"] == "Released"), "link": "/offers?status=Released"})
    if can(user, "cost.view"):
        pending.append({"key": "cost", "label": "Awaiting joining cost confirmation", "count": sum(1 for a in apps if a["status"] == "Offer Accepted" and not a.get("hire_cost")),
                        "link": "/pipeline?status=Offer Accepted"})

    order = PIPELINE + [s for s in by_status if s not in PIPELINE]
    distribution = [{"status": s, "count": by_status[s], "active": s not in INACTIVE} for s in order if by_status.get(s)]

    return {"period": {"key": period, "start": start.isoformat(), "end": end.isoformat(), "previous_start": pstart.isoformat(),
                       "previous_end": pend.isoformat(), "granularity": gran},
            "hero": hero, "trend": {"series": [{"key": k, "label": l} for k, l in series_kinds], "points": trend},
            "funnel": {"stages": funnel, "overall_conversion": overall, "cohort": len(cohort)},
            "cost": cost, "age_per_hire": age, "sources": sources, "recruiters": recruiters, "requisitions": requisitions,
            "upcoming_interviews": upcoming, "activity": feed, "pending": pending, "distribution": distribution,
            "total_applications": len(apps)}
