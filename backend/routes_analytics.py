import csv
import io
from collections import defaultdict
from statistics import median
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font

from core import (db, get_user, require, can, today, days_between, effective_start, log_activity, PIPELINE,
                  IMPLIED_STAGE, INACTIVE)
from routes_recruit import list_applications, list_requisitions, list_candidates
from routes_interviews import list_interviews
from routes_offers import list_offers, list_joinings, list_costs

router = APIRouter(prefix="/api")
FUNNEL = [("Candidates Sourced", 0), ("Screening", 1), ("Shortlisted", 2), ("Interviewed", 4), ("Selected", 6),
          ("Offers Released", 8), ("Offers Accepted", 9), ("Joined", 10)]


def stage_idx(a):
    idx = 0
    for s in [h["status"] for h in a.get("history", [])] + [a["status"]]:
        if s in PIPELINE:
            idx = max(idx, PIPELINE.index(s))
        elif s in IMPLIED_STAGE:
            idx = max(idx, IMPLIED_STAGE[s])
    return idx


def pct(a, b):
    return round(a * 100 / b, 1) if b else None


def stats(vals):
    vals = [v for v in vals if v is not None]
    return {"avg": round(sum(vals) / len(vals), 1) if vals else None, "median": median(vals) if vals else None, "count": len(vals)}


def aph_stats(vals):
    vals = [v for v in vals if v is not None]
    return stats(vals) | {"min": min(vals) if vals else None, "max": max(vals) if vals else None}


def quarter(d):
    return f"{d[:4]}-Q{(int(d[5:7]) - 1) // 3 + 1}"


def prev_period(key):
    if "-Q" in key:
        y, q = int(key[:4]), int(key[-1])
        return f"{y - 1}-Q4" if q == 1 else f"{y}-Q{q - 1}"
    y, m = int(key[:4]), int(key[5:7])
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def aph_value(a, rmap):
    """Age per Hire = Actual DOJ - CRF Raised Date (no substitution)."""
    crf = rmap.get(a["requisition_id"], {}).get("crf_date")
    if not crf:
        return None, "CRF Raised Date missing on requisition"
    if not a.get("_join"):
        return None, "Actual date of joining missing"
    d = days_between(crf, a["_join"])
    if d < 0:
        return None, "Joining date precedes CRF Raised Date"
    return d, None


def age_per_hire(apps_all, hires, reqs, rmap, dated):
    """Age per Hire (days) = Actual Date of Joining - CRF Raised Date.

    * Only applications with status Joined AND a joining record with an actual date count as completed hires.
    * The CRF Raised Date is never substituted (no fallback to initiation / creation date).
    * Missing CRF, missing DOJ or DOJ before CRF -> value is None and the hire is flagged for HR data completion.
    """
    all_hires = [a for a in apps_all if a["status"] == "Joined"]
    for a in all_hires:
        a["_aph"], a["_aph_flag"] = aph_value(a, rmap)
    valid = [a for a in hires if a["_aph"] is not None]

    def by(key):
        g = defaultdict(list)
        for a in valid:
            g[a.get(key) or "—"].append(a["_aph"])
        return sorted([{"name": k, **aph_stats(v)} for k, v in g.items()], key=lambda x: -x["count"])

    def series(rows):
        monthly, quarterly = defaultdict(list), defaultdict(list)
        for a in rows:
            if a["_aph"] is not None:
                monthly[a["_join"][:7]].append(a["_aph"])
                quarterly[quarter(a["_join"])].append(a["_aph"])
        return monthly, quarterly

    # Trend follows the date filter when one is set; period-over-period comparison is always relative to today.
    monthly, quarterly = series(hires if dated else all_hires)
    cmp_monthly, cmp_quarterly = series(all_hires)

    def compare(sr, key):
        cur, prev = stats(sr.get(key, [])), stats(sr.get(prev_period(key), []))
        return {"period": key, "avg": cur["avg"], "count": cur["count"], "previous_period": prev_period(key),
                "previous_avg": prev["avg"], "previous_count": prev["count"],
                "change": round(cur["avg"] - prev["avg"], 1) if cur["avg"] is not None and prev["avg"] is not None else None}

    t = today()
    # Current Hiring Age = Today - CRF Raised Date, per ongoing (Open / On Hold) requisition — a separate metric.
    ongoing, missing = [], []
    for r in reqs:
        if r.get("status") not in ("Open", "On Hold"):
            continue
        crf = r.get("crf_date")
        if crf and crf <= t:
            ongoing.append(days_between(crf, t))
        else:
            missing.append({"code": r.get("code"), "title": r.get("title"), "id": r.get("id"),
                            "issue": "CRF Raised Date missing" if not crf else "CRF Raised Date is in the future"})
    return {"completed": aph_stats([a["_aph"] for a in valid]),
            "by_department": by("department"), "by_role": by("requisition_title"), "by_recruiter": by("recruiter"),
            "by_partner": by("partner"), "by_source": by("source"),
            "monthly": [{"period": k, **aph_stats(v)} for k, v in sorted(monthly.items())][-12:],
            "quarterly": [{"period": k, **aph_stats(v)} for k, v in sorted(quarterly.items())][-8:],
            "month_compare": compare(cmp_monthly, t[:7]), "quarter_compare": compare(cmp_quarterly, quarter(t)),
            "current_hiring_age": aph_stats(ongoing) | {"missing_crf": len(missing)},
            "incomplete_requisitions": missing,
            "hires": [{"candidate": a["candidate_name"], "code": a["code"], "role": a["requisition_title"],
                       "requisition_code": a.get("requisition_code"), "department": a.get("department"),
                       "recruiter": a.get("recruiter"), "partner": a.get("partner"), "source": a.get("source"),
                       "crf_date": rmap.get(a["requisition_id"], {}).get("crf_date"), "joined_on": a["_join"],
                       "days": a["_aph"], "flag": a["_aph_flag"]} for a in hires],
            "flagged": sum(1 for a in hires if a["_aph_flag"])}


def in_range(d, f):
    if not d:
        return False
    return (not f.get("date_from") or d >= f["date_from"]) and (not f.get("date_to") or d <= f["date_to"])


async def compute(user, f):
    base = {k: f.get(k) for k in ("requisition_id", "recruiter_id", "department_id", "source_id", "partner_id")}
    apps_all = await list_applications(user, base)
    if f.get("role"):
        apps_all = [a for a in apps_all if f["role"].lower() in (a.get("requisition_title") or "").lower()]
    if f.get("role_exact"):
        apps_all = [a for a in apps_all if f["role_exact"].strip().lower() == (a.get("requisition_title") or "").strip().lower()]
    rids = list({a["requisition_id"] for a in apps_all})
    rmap = {r["id"]: r async for r in db.requisitions.find({"id": {"$in": rids}}, {"_id": 0})}
    jmap = {j["application_id"]: j async for j in db.joinings.find({"status": "Joined"}, {"_id": 0})}
    for a in apps_all:
        a["_idx"] = stage_idx(a)
        j = jmap.get(a["id"])
        a["_join"] = (j or {}).get("actual_date")
        start = effective_start(rmap.get(a["requisition_id"], {}))
        a["_cycle"] = days_between(start, a["_join"]) if start and a["_join"] and a["status"] == "Joined" else None
        a["_age"] = days_between(start, today()) if start and a["status"] not in INACTIVE else None
    dated = bool(f.get("date_from") or f.get("date_to"))
    apps = [a for a in apps_all if not dated or in_range(a["created_at"][:10], f)]
    if f.get("status"):
        apps = [a for a in apps if a["status"] == f["status"]]
    hires = [a for a in apps_all if a["status"] == "Joined" and (not dated or in_range(a["_join"] or a["stage_entered_at"][:10], f))]
    reqs = await list_requisitions(user, {k: f.get(k) for k in ("department_id", "recruiter_id")})
    if f.get("requisition_id"):
        reqs = [r for r in reqs if r["id"] == f["requisition_id"]]
    if f.get("role"):
        reqs = [r for r in reqs if f["role"].lower() in (r.get("title") or "").lower()]
    if f.get("role_exact"):
        reqs = [r for r in reqs if f["role_exact"].strip().lower() == (r.get("title") or "").strip().lower()]
    open_reqs = [r for r in reqs if r["status"] == "Open"]
    ivs = await list_interviews(user, {k: f.get(k) for k in ("requisition_id",)})
    app_ids = {a["id"] for a in apps}
    ivs = [i for i in ivs if i["application_id"] in app_ids]

    def count(cond, rows=apps):
        return sum(1 for a in rows if cond(a))

    by_status = defaultdict(int)
    for a in apps:
        by_status[a["status"]] += 1
    kpis = {"open_requisitions": len(open_reqs), "open_positions": sum(r["open_positions"] for r in open_reqs),
            "total_candidates": len({a["candidate_id"] for a in apps}), "total_applications": len(apps),
            "in_process": count(lambda a: a["status"] not in INACTIVE),
            "interviews_scheduled": sum(1 for i in ivs if i["status"] in ("Scheduled", "Rescheduled")),
            "offers_released": count(lambda a: a["_idx"] >= 8), "offers_accepted": count(lambda a: a["_idx"] >= 9),
            "joined": len(hires), "cv_rejections": by_status.get("CV Rejected", 0),
            "interview_rejections": by_status.get("Interview Rejected", 0), "offer_declines": by_status.get("Offer Declined", 0),
            "offer_revocations": by_status.get("Offer Revoked", 0), "on_hold": by_status.get("On Hold", 0),
            "stuck": count(lambda a: a["stuck"])}
    if not any(f.get(k) for k in ("requisition_id", "department_id", "role", "role_exact", "status")) and can(user, "cand.view"):
        cands = await list_candidates(user, {k: f.get(k) for k in ("source_id", "partner_id", "recruiter_id")})
        kpis["total_candidates"] = len([c for c in cands if not dated or in_range(c["created_at"][:10], f)])
    funnel, prev = [], None
    for label, idx in FUNNEL:
        n = count(lambda a: a["_idx"] >= idx) if idx < 10 else count(lambda a: a["status"] == "Joined")
        funnel.append({"stage": label, "count": n, "conversion": pct(n, prev) if prev is not None else 100.0 if n else None,
                       "of_total": pct(n, len(apps))})
        prev = n

    costs = await list_costs(user, {k: f.get(k) for k in ("date_from", "date_to", "department_id", "role", "recruiter_id", "partner_id", "requisition_id")}) if can(user, "cost.view") else None

    def group(key_fn, rows):
        g = defaultdict(list)
        for a in rows:
            g[key_fn(a)].append(a)
        return g

    def perf(rows, hires_rows):
        return {"total": len(rows), "in_process": count(lambda a: a["status"] not in INACTIVE, rows),
                "screened": count(lambda a: a["_idx"] >= 1, rows), "shortlisted": count(lambda a: a["_idx"] >= 2, rows),
                "interviewed": count(lambda a: a["_idx"] >= 4, rows), "selected": count(lambda a: a["_idx"] >= 6, rows),
                "offers_released": count(lambda a: a["_idx"] >= 8, rows), "offers_accepted": count(lambda a: a["_idx"] >= 9, rows),
                "joined": len(hires_rows), "conversion": pct(len(hires_rows), len(rows)),
                "avg_cycle": stats([a["_cycle"] for a in hires_rows])["avg"]}

    # Cost per hire (one hire) = candidate annual CTC + consulting fees + recruiter fees, confirmed before joining.
    # Average cost per hire = sum of those totals ÷ joined candidates with confirmed cost (same filters as the joiners).
    def cost_for(field, key, hire_rows=()):
        if costs is None:
            return None, 0
        done = [a["hire_cost"]["total"] for a in hire_rows if a.get("hire_cost")]
        return round(sum(done), 2), len(done)

    recruiters = []
    hg = group(lambda a: a.get("recruiter_id"), hires)
    for rid, rows in group(lambda a: a.get("recruiter_id"), apps).items():
        p = perf(rows, hg.get(rid, []))
        total_cost, n_cost = cost_for("recruiter_id", rid, hg.get(rid, []))
        p |= {"recruiter_id": rid, "name": rows[0].get("recruiter") or "Unassigned", "total_cost": total_cost,
              "cost_per_hire": round(total_cost / n_cost, 2) if total_cost is not None and n_cost else None,
              "workload": p["in_process"], "open_requisitions": sum(1 for r in open_reqs if r.get("recruiter_id") == rid)}
        recruiters.append(p)

    roles = []
    ag, hgr = group(lambda a: a["requisition_id"], apps), group(lambda a: a["requisition_id"], hires)
    for r in reqs:
        rows = ag.get(r["id"], [])
        roles.append({"id": r["id"], "code": r["code"], "title": r["title"], "department": r.get("department") or "—",
                      "status": r["status"], "positions": r.get("positions") or 0, "filled": r.get("filled_positions") or 0,
                      "open": r["open_positions"], "candidates": len(rows),
                      "in_process": count(lambda a: a["status"] not in INACTIVE, rows),
                      "avg_cycle": stats([a["_cycle"] for a in hgr.get(r["id"], [])])["avg"], "age_days": r.get("age_days")})
    depts = defaultdict(lambda: {"positions": 0, "filled": 0, "open": 0, "candidates": 0, "in_process": 0, "requisitions": 0})
    for r in roles:
        d = depts[r["department"]]
        d["requisitions"] += 1
        for k in ("positions", "filled", "open", "candidates", "in_process"):
            d[k] += r[k]
    hd = group(lambda a: a.get("department") or "—", hires)
    departments = [{"department": k, **v, "joined": len(hd.get(k, [])), "avg_cycle": stats([a["_cycle"] for a in hd.get(k, [])])["avg"]} for k, v in depts.items()]

    sources = []
    hs = group(lambda a: a.get("source") or "Unknown", hires)
    for s, rows in group(lambda a: a.get("source") or "Unknown", apps).items():
        p = perf(rows, hs.get(s, []))
        p |= {"source": s, "screening_conversion": pct(p["shortlisted"], p["screened"]),
              "interview_conversion": pct(p["selected"], p["interviewed"])}
        sources.append(p)
    partners = []
    hp = group(lambda a: a.get("partner_id"), hires)
    for pid, rows in group(lambda a: a.get("partner_id"), apps).items():
        if not pid:
            continue
        p = perf(rows, hp.get(pid, []))
        tc, n_cost = cost_for("partner_id", pid, hp.get(pid, []))
        p |= {"partner": rows[0].get("partner"), "total_cost": tc,
              "cost_per_hire": round(tc / n_cost, 2) if tc is not None and n_cost else None}
        partners.append(p)

    cost = None
    if costs is not None:
        invoiced = round(sum(c.get("amount") or 0 for c in costs), 2)
        cats = defaultdict(float)
        months = defaultdict(float)
        for c in costs:
            cats[c.get("category") or "Uncategorised"] += c.get("amount") or 0
            months[(c.get("invoice_date") or "")[:7]] += c.get("amount") or 0
        confirmed = [a for a in hires if a.get("hire_cost")]
        tot = lambda k: round(sum(a["hire_cost"][k] for a in confirmed), 2)
        total = tot("total")
        cost = {"formula": "Cost per Hire = Candidate annual CTC + Consulting fees + Recruiter fees; "
                           "Average = sum of Cost per Hire for joined candidates with confirmed cost ÷ number of those candidates",
                "total": total, "ctc_total": tot("ctc"), "consulting_total": tot("consulting_fee"), "recruiter_total": tot("recruiter_fee"),
                "fees": round(tot("consulting_fee") + tot("recruiter_fee"), 2),
                "hires": len(confirmed), "joined": len(hires), "unconfirmed": len(hires) - len(confirmed),
                "cost_per_hire": round(total / len(confirmed), 2) if confirmed else None,
                "hire_costs": [{"application_id": a["id"], "code": a["code"], "candidate": a["candidate_name"], "requisition_code": a.get("requisition_code"),
                                "role": a["requisition_title"], "department": a.get("department"), "recruiter": a.get("recruiter"), "partner": a.get("partner"),
                                "joined_on": a["_join"], **({k: a["hire_cost"][k] for k in ("ctc", "consulting_fee", "recruiter_fee", "total", "confirmed_by", "confirmed_at", "updated_by", "updated_at")}
                                                            if a.get("hire_cost") else {"total": None, "flag": "Cost not confirmed — not counted as a completed hire"})}
                               for a in hires],
                "invoiced": invoiced,
                "amount_pending": sum(1 for c in costs if c.get("amount") is None),
                "by_category": [{"category": k, "amount": round(v, 2)} for k, v in cats.items()],
                "by_month": [{"month": k, "amount": round(v, 2)} for k, v in sorted(months.items()) if k],
                "paid": round(sum(c["amount"] or 0 for c in costs if c.get("payment_status") == "Paid"), 2)}

    def cycle_by(key):
        return [{"name": k or "—", **stats([a["_cycle"] for a in rows])} for k, rows in group(lambda a: a.get(key), hires).items()]

    active = [a for a in apps if a["_age"] is not None]
    cycle = {"label": "Recruitment cycle time — from the earlier of CRF Raised / Recruitment Initiation Date (not Age per Hire)",
             "completed": stats([a["_cycle"] for a in hires]), "current_age": stats([a["_age"] for a in active]),
             "by_role": cycle_by("requisition_title"), "by_department": cycle_by("department"),
             "by_recruiter": cycle_by("recruiter"), "by_source": cycle_by("source"),
             "hires": [{"candidate": a["candidate_name"], "role": a["requisition_title"], "joined_on": a["_join"], "days": a["_cycle"]} for a in hires],
             "oldest_active": sorted([{"candidate": a["candidate_name"], "role": a["requisition_title"], "status": a["status"], "age": a["_age"]} for a in active], key=lambda x: -x["age"])[:15],
             "missing_join_date": sum(1 for a in hires if a["_cycle"] is None)}

    aph = age_per_hire(apps_all, hires, reqs, rmap, dated)

    months = defaultdict(lambda: {"applications": 0, "offers": 0, "joined": 0})
    for a in apps_all:
        months[a["created_at"][:7]]["applications"] += 1
        if a["_join"]:
            months[a["_join"][:7]]["joined"] += 1
    if can(user, "offer.view"):
        for o in await list_offers(user, {}):
            if o.get("release_date") and o["application_id"] in {x["id"] for x in apps_all}:
                months[o["release_date"][:7]]["offers"] += 1
    trends = [{"month": k, **v} for k, v in sorted(months.items())][-12:]
    status_breakdown = [{"status": k, "count": v} for k, v in sorted(by_status.items(), key=lambda x: -x[1])]
    return {"kpis": kpis, "funnel": funnel, "recruiters": recruiters, "roles": roles, "departments": departments,
            "sources": sources, "partners": partners, "cost": cost, "cycle": cycle, "trends": trends, "aph": aph,
            "status_breakdown": status_breakdown}


@router.get("/analytics")
async def analytics(request: Request, user=Depends(require("analytics.view"))):
    return await compute(user, dict(request.query_params))


# ---------- reports ----------
def col(*pairs):
    return list(pairs)


REPORTS = {
    "candidates": ("cand.view", lambda u, f: list_candidates(u, f), col(("Candidate ID", "code"), ("Name", "name"), ("Email", "email"), ("Mobile", "phone"),
                   ("Current Company", "current_company"), ("Designation", "current_designation"), ("Location", "current_location"),
                   ("Total Exp (yrs)", "total_exp"), ("Relevant Exp", "relevant_exp"), ("Qualification", "qualification"),
                   ("Current CTC (L)", "current_ctc"), ("Expected CTC (L)", "expected_ctc"), ("Notice Period", "notice_period"),
                   ("Source", "source"), ("Partner", "partner"), ("Recruiter", "recruiter"), ("Roles", "roles"),
                   ("Latest Status", "latest_status"), ("Remarks", "remarks"), ("Created", "created_at"))),
    "requisitions": ("req.view", lambda u, f: list_requisitions(u, f), col(("Requisition ID", "code"), ("Job Title", "title"), ("Department", "department"),
                     ("Hiring Manager", "hiring_manager"), ("Recruiter", "recruiter"), ("Positions", "positions"), ("Filled", "filled_positions"),
                     ("Open", "open_positions"), ("Experience", "experience"), ("Min CTC (L)", "min_ctc"), ("Max CTC (L)", "max_ctc"),
                     ("Location", "location"), ("Priority", "priority"), ("Status", "status"), ("CRF Raised", "crf_date"),
                     ("Initiation", "initiation_date"), ("Effective Start", "effective_start"), ("Age (days)", "age_days"),
                     ("Candidates", "candidates_count"), ("Active", "active_count"), ("Remarks", "remarks"))),
    "pipeline": ("app.view", lambda u, f: list_applications(u, f), col(("Application ID", "code"), ("Candidate", "candidate_name"), ("Email", "candidate_email"),
                 ("Requisition", "requisition_code"), ("Role", "requisition_title"), ("Department", "department"), ("Recruiter", "recruiter"),
                 ("Source", "source"), ("Partner", "partner"), ("Status", "status"), ("Days in Stage", "days_in_stage"),
                 ("Recruitment Age", "recruitment_age"), ("Created", "created_at"))),
    "interviews": ("interview.view", lambda u, f: list_interviews(u, f), col(("Interview ID", "code"), ("Candidate", "candidate_name"), ("Role", "requisition_title"),
                   ("Round #", "round_number"), ("Round", "round_name"), ("Type", "round_type"), ("Date", "date"), ("Start", "start_time"),
                   ("End", "end_time"), ("Mode", "mode"), ("Interviewers", lambda r: ", ".join(x for x in r["interviewers"] if x)),
                   ("Location / Link", "location"), ("Status", "status"), ("Feedback", "feedback_status"), ("Outcome", "outcome"))),
    "offers": ("offer.view", lambda u, f: list_offers(u, f), col(("Offer ID", "code"), ("Candidate", "candidate_name"), ("Role", "requisition_title"),
               ("Designation", "designation"), ("CTC (L)", "ctc"), ("Fixed", "fixed"), ("Variable", "variable"), ("Other", "other"),
               ("Status", "status"), ("Approval", "approval_status"), ("Released", "release_date"), ("Valid Until", "validity_date"),
               ("Accepted", "accepted_date"), ("Declined", "declined_date"), ("Decline Reason", "decline_reason"))),
    "joinings": ("joining.view", lambda u, f: list_joinings(u, f), col(("Joining ID", "code"), ("Candidate", "candidate_name"), ("Role", "requisition_title"),
                 ("Recruiter", "recruiter"), ("Partner", "partner"), ("Tentative", "tentative_date"), ("Confirmed", "confirmed_date"),
                 ("Actual DOJ", "actual_date"), ("Status", "status"),
                 ("Documents Received", lambda r: f"{sum(1 for c in r.get('checklist', []) if c.get('received'))}/{len(r.get('checklist', []))}"),
                 ("Remarks", "remarks"))),
    "costs": ("cost.view", lambda u, f: list_costs(u, f), col(("Cost ID", "code"), ("Category", "category"), ("Recruiter", "recruiter"), ("Partner", "partner"),
              ("Requisition", "requisition_code"), ("Role", "requisition_title"), ("Department", "department"), ("Candidate", "candidate_name"),
              ("Invoice #", "invoice_no"), ("Invoice Date", "invoice_date"), ("Amount (L)", "amount"), ("Payment", "payment_status"),
              ("Paid On", "payment_date"), ("Remarks", "remarks"))),
}


def period_key(d, mode):
    if not d:
        return None
    if mode == "quarterly":
        return f"{d[:4]}-Q{(int(d[5:7]) - 1) // 3 + 1}"
    return d[:7]


async def summary_rows(user, f, mode):
    data = await compute(user, {k: v for k, v in f.items() if k not in ("date_from", "date_to")})
    apps = await list_applications(user, {k: f.get(k) for k in ("requisition_id", "recruiter_id", "department_id", "source_id", "partner_id")})
    p = defaultdict(lambda: {"Applications": 0, "Offers Released": 0, "Offers Accepted": 0, "Joined": 0, "Rejections": 0, "Interviews": 0, "Cost (L)": 0.0, "Hires with Confirmed Cost": 0})
    for a in apps:
        p[period_key(a["created_at"][:10], mode)]["Applications"] += 1
        for h in a.get("history", []):
            k = period_key(h["at"][:10], mode)
            if h["status"] == "Offer Released":
                p[k]["Offers Released"] += 1
            elif h["status"] == "Offer Accepted":
                p[k]["Offers Accepted"] += 1
            elif h["status"] in ("CV Rejected", "Interview Rejected"):
                p[k]["Rejections"] += 1
    for h in data["cycle"]["hires"]:
        if h["joined_on"]:
            p[period_key(h["joined_on"], mode)]["Joined"] += 1
    for i in await list_interviews(user, {}):
        p[period_key(i.get("date"), mode)]["Interviews"] += 1
    if data.get("cost"):
        for h in data["cost"]["hire_costs"]:
            if h["joined_on"] and h.get("total") is not None:
                k = period_key(h["joined_on"], mode)
                p[k]["Cost (L)"] += h["total"]
                p[k]["Hires with Confirmed Cost"] += 1
    rows = []
    for k in sorted(x for x in p if x):
        if (f.get("date_from") and k < period_key(f["date_from"], mode)) or (f.get("date_to") and k > period_key(f["date_to"], mode)):
            continue
        v = p[k]
        v["Cost per Hire (L)"] = round(v["Cost (L)"] / v["Hires with Confirmed Cost"], 2) if v.get("Hires with Confirmed Cost") else "N/A"
        v["Cost (L)"] = round(v["Cost (L)"], 2)
        rows.append({"Period": k, **v})
    return rows


def to_file(headers, rows, fmt, name):
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(headers)
        w.writerows(rows)
        data, mt = buf.getvalue().encode("utf-8-sig"), "text/csv"
    else:
        wb = Workbook()
        ws = wb.active
        ws.title = name[:30]
        ws.append(headers)
        for c in ws[1]:
            c.font = Font(bold=True)
        for r in rows:
            ws.append(r)
        buf = io.BytesIO()
        wb.save(buf)
        data, mt = buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return StreamingResponse(io.BytesIO(data), media_type=mt,
                             headers={"Content-Disposition": f'attachment; filename="mms-{name}-{today()}.{fmt}"'})


@router.get("/reports/{rtype}")
async def export_report(rtype: str, request: Request, user=Depends(get_user)):
    f = dict(request.query_params)
    fmt = "csv" if f.pop("format", "xlsx") == "csv" else "xlsx"
    if rtype == "cost-per-hire":
        if not can(user, "cost.view") or not can(user, "reports.export"):
            raise HTTPException(403, "Not permitted")
        hs = ((await compute(user, f)).get("cost") or {}).get("hire_costs", [])
        heads = [("Application", "code"), ("Candidate", "candidate"), ("Requisition", "requisition_code"), ("Role", "role"), ("Department", "department"),
                 ("Recruiter", "recruiter"), ("Partner", "partner"), ("Actual DOJ", "joined_on"), ("Annual CTC (L)", "ctc"),
                 ("Consulting Fees (L)", "consulting_fee"), ("Recruiter Fees (L)", "recruiter_fee"), ("Cost per Hire (L)", "total"),
                 ("Confirmed By", "confirmed_by"), ("Confirmed At", "confirmed_at"), ("Last Updated By", "updated_by"), ("Flag", "flag")]
        await log_activity(user, "export", "report", rtype, rtype, f"{len(hs)} rows ({fmt})")
        return to_file([h for h, _ in heads], [[r.get(k) for _, k in heads] for r in hs], fmt, "cost-per-hire")
    if rtype == "age-per-hire":
        if not can(user, "analytics.view") or not can(user, "reports.export"):
            raise HTTPException(403, "Not permitted")
        hs = (await compute(user, f))["aph"]["hires"]
        heads = [("Application", "code"), ("Candidate", "candidate"), ("Requisition", "requisition_code"), ("Role", "role"),
                 ("Department", "department"), ("Recruiter", "recruiter"), ("Partner", "partner"), ("Source", "source"),
                 ("CRF Raised Date", "crf_date"), ("Actual DOJ", "joined_on"), ("Age per Hire (days)", "days"), ("Data Flag", "flag")]
        return to_file([h for h, _ in heads], [[r.get(k) for _, k in heads] for r in hs], fmt, "age-per-hire")
    if rtype in ("summary", "recruiters", "funnel", "sources", "departments"):
        if not can(user, "analytics.view") or not can(user, "reports.export"):
            raise HTTPException(403, "Not permitted")
        if rtype == "summary":
            rows = await summary_rows(user, f, f.get("period", "monthly"))
            headers = list(rows[0].keys()) if rows else ["Period"]
            return to_file(headers, [list(r.values()) for r in rows], fmt, f"summary-{f.get('period', 'monthly')}")
        data = await compute(user, f)
        key = {"recruiters": "recruiters", "funnel": "funnel", "sources": "sources", "departments": "departments"}[rtype]
        rows = data[key]
        headers = list(rows[0].keys()) if rows else ["No data"]
        headers = [h for h in headers if not h.endswith("_id")]
        return to_file(headers, [[r.get(h) for h in headers] for r in rows], fmt, rtype)
    if rtype not in REPORTS:
        raise HTTPException(404, "Unknown report")
    perm, fn, cols = REPORTS[rtype]
    if not can(user, perm) or not can(user, "reports.export") and rtype != "interviews":
        raise HTTPException(403, "Not permitted")
    rows = await fn(user, f)
    out = [[(c(r) if callable(c) else r.get(c)) for _, c in cols] for r in rows]
    await log_activity(user, "export", "report", rtype, rtype, f"{len(out)} rows ({fmt})")
    return to_file([h for h, _ in cols], out, fmt, rtype)
