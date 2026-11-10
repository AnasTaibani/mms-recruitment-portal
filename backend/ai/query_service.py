"""Read-only, permission-scoped retrieval for the assistant.

Every function reuses the portal's existing list_* services (which apply get_scope / record scope) and checks the
same permissions the corresponding pages require. Only compact, minimal fields are returned — no contact details,
no salaries/CTC unless the user can see costs, no free-text remarks."""
import re
from collections import Counter, defaultdict
from datetime import date

from core import can, db, now_iso, today, PIPELINE, TERMINAL
from routes_recruit import list_requisitions, list_applications, list_candidates
from routes_interviews import list_interviews
from routes_offers import list_offers, list_joinings
from routes_analytics import compute

MAX_REQS = 25
MAX_ROWS = 12
STOP = {"the", "and", "of", "for", "a", "an", "requirement", "requirements", "requisition", "requisitions", "role", "roles", "position", "positions", "opening", "openings", "hiring"}
ALIASES = {"ba": ["business analyst"], "qa": ["quality assurance", "qa", "tester", "test engineer"], "pm": ["project manager", "product manager"],
           "hr": ["human resources", "hr"], "ui": ["ui", "user interface"], "ux": ["ux", "user experience"], "dev": ["developer", "engineer"]}
INTERVIEW_STAGES = ["Interview Scheduled", "Interview In Progress", "Interview Completed"]
OFFER_STAGES = ["Offer Approval Pending", "Offer Released", "Offer Accepted"]


def clip(v, n=90):
    return v[:n] if isinstance(v, str) else v


def _acronyms(title):
    words = [w for w in re.findall(r"[A-Za-z]+", title)]
    out = set()
    for i in range(len(words)):
        for j in range(i + 1, min(len(words), i + 4) + 1):
            out.add("".join(w[0] for w in words[i:j]).lower())
    return out


def title_matches(title: str, query: str) -> bool:
    t, q = (title or "").lower(), (query or "").lower().strip()
    if not q:
        return True
    # short queries ("BA", "QA") must match a whole word, otherwise "ba" would hit "Database Engineer"
    if (re.search(rf"(?<![a-z0-9]){re.escape(q)}(?![a-z0-9])", t) if len(q) <= 4 else q in t):
        return True
    tokens = [w for w in re.findall(r"[a-z0-9+#.]+", q) if w not in STOP]
    if not tokens:
        return False
    if len(tokens) == 1 and tokens[0] in ALIASES and any(a in t for a in ALIASES[tokens[0]]):
        return True
    if len(tokens) == 1 and len(tokens[0]) <= 4 and tokens[0] in _acronyms(title or ""):
        return True
    return all(re.search(rf"\b{re.escape(w)}", t) for w in tokens)


def _name_match(name, q):
    return bool(q) and q.lower() in (name or "").lower()


async def resolve_requisitions(user, scope: dict):
    """Requisitions visible to the user that match the requested scope."""
    reqs = await list_requisitions(user, {})
    rq, dept, rec = scope.get("requisition_query"), scope.get("department"), scope.get("recruiter")
    out = [r for r in reqs if title_matches(r.get("title"), rq) and (not dept or _name_match(r.get("department"), dept))
           and (not rec or _name_match(r.get("recruiter"), rec))]
    return out, reqs


def _req_row(r, n_apps=None):
    return {"code": r.get("code"), "title": clip(r.get("title")), "status": r.get("status"), "department": clip(r.get("department"), 50),
            "location": clip(r.get("location"), 40), "recruiter": clip(r.get("recruiter"), 50) or None, "hiring_manager": clip(r.get("hiring_manager"), 50) or None,
            "approved_positions": r.get("positions") or 0, "filled_positions": r.get("filled_positions") or 0,
            "remaining_positions": r.get("open_positions") if r.get("status") in ("Open", "On Hold") else 0,
            "crf_raised": r.get("crf_date"), "days_open": r.get("current_hiring_age"), **({"applications": n_apps} if n_apps is not None else {})}


async def recruitment_snapshot(user, scope: dict, focus: list):
    """Requirement-level recruitment snapshot (the BA-requirements use case and its follow-ups)."""
    missing = []
    reqs, all_reqs = await resolve_requisitions(user, scope)
    any_filter = any(scope.get(k) for k in ("requisition_query", "department", "recruiter"))
    snap = {"scope": {k: v for k, v in scope.items() if v} or "all requisitions you can access", "retrieved_at": now_iso(), "today": today()}
    if any_filter and not reqs:
        open_titles = sorted({r["title"] for r in all_reqs if r.get("status") == "Open"})[:15]
        snap["no_match"] = True
        snap["open_requisition_titles_you_can_access"] = open_titles
        return snap, reqs, missing
    rids = {r["id"] for r in reqs}

    apps = []
    if can(user, "app.view"):
        apps = [a for a in await list_applications(user, {}) if a["requisition_id"] in rids]
    else:
        missing.append("candidate pipeline (your role cannot view applications)")
    per_req = Counter(a["requisition_id"] for a in apps)
    active_reqs = [r for r in reqs if r.get("status") in ("Open", "On Hold")]
    snap["requisitions"] = {
        "matched": len(reqs), "by_status": dict(Counter(r.get("status") for r in reqs)),
        "approved_positions_active": sum(r.get("positions") or 0 for r in active_reqs),
        "filled_positions_active": sum(r.get("filled_positions") or 0 for r in active_reqs),
        "remaining_positions_active": sum(r.get("open_positions") or 0 for r in active_reqs),
        "approved_positions_all": sum(r.get("positions") or 0 for r in reqs), "filled_positions_all": sum(r.get("filled_positions") or 0 for r in reqs),
        "list": [_req_row(r, per_req.get(r["id"], 0) if can(user, "app.view") else None)
                 for r in sorted(reqs, key=lambda r: (r.get("status") != "Open", -(per_req.get(r["id"], 0))))[:MAX_REQS]],
        "note": "‘active’ = requisitions in Open or On Hold; remaining = approved − filled for those.",
    }
    if len(reqs) > MAX_REQS:
        snap["requisitions"]["truncated"] = f"showing {MAX_REQS} of {len(reqs)}"

    if can(user, "app.view"):
        by_status = Counter(a["status"] for a in apps)
        order = [s for s in PIPELINE + TERMINAL if by_status.get(s)]
        snap["pipeline"] = {
            "total_applications": len(apps), "unique_candidates": len({a["candidate_id"] for a in apps}),
            "active_applications": sum(1 for a in apps if not a.get("closed")),
            "applications_by_current_stage": {s: by_status[s] for s in order},
            "grouped": {"Screening": by_status.get("Screening", 0), "Shortlisted": by_status.get("Shortlisted", 0),
                        "Interview (scheduled / in progress / completed)": sum(by_status.get(s, 0) for s in INTERVIEW_STAGES),
                        "Selected": by_status.get("Selected", 0), "Offer (approval pending / released / accepted)": sum(by_status.get(s, 0) for s in OFFER_STAGES),
                        "Joined": by_status.get("Joined", 0)},
            "note": "Counts are applications by their CURRENT stage (one candidate can have applications on several requisitions).",
        }
        if "candidates" in focus or scope.get("stage"):
            st = (scope.get("stage") or "").lower()
            rows = [a for a in apps if not st or st in a["status"].lower()]
            snap["pipeline"]["applications_sample"] = [{"candidate": clip(a.get("candidate_name"), 60), "requisition": a.get("requisition_code"),
                                                        "stage": a["status"], "days_in_stage": a.get("days_in_stage")} for a in rows[:MAX_ROWS]]
            if len(rows) > MAX_ROWS:
                snap["pipeline"]["applications_sample_note"] = f"first {MAX_ROWS} of {len(rows)}"

    # recruiter allocation: requisition owners plus who holds the applications
    rec = defaultdict(lambda: {"requisitions": [], "applications": 0})
    for r in reqs:
        rec[r.get("recruiter") or "Unassigned"]["requisitions"].append(r.get("code"))
    for a in apps:
        rec[a.get("recruiter") or "Unassigned"]["applications"] += 1
    snap["recruiters"] = [{"recruiter": clip(k, 60), "requisitions": v["requisitions"][:10], **({"applications": v["applications"]} if can(user, "app.view") else {})}
                          for k, v in sorted(rec.items(), key=lambda kv: -len(kv[1]["requisitions"]))]

    if can(user, "interview.view"):
        app_ids = {a["id"] for a in apps}
        # counts follow the portal's dashboards (applications in view); details only for interviews the user may open
        if app_ids:
            counts = [i async for i in db.interviews.find({"application_id": {"$in": list(app_ids)}}, {"_id": 0, "status": 1, "feedback_status": 1, "date": 1})]
        else:
            counts = [i for i in await list_interviews(user, {}) if i["requisition_id"] in rids]
        visible = [i for i in await list_interviews(user, {}) if i["requisition_id"] in rids]
        t = today()
        upcoming = sorted([i for i in visible if i.get("status") in ("Scheduled", "Rescheduled") and (i.get("date") or "") >= t], key=lambda i: (i["date"], i.get("start_time") or ""))
        snap["interviews"] = {
            "total": len(counts), "by_status": dict(Counter(i.get("status") for i in counts)),
            "feedback_pending_on_past_or_completed": sum(1 for i in counts if i.get("status") in ("Scheduled", "Rescheduled", "Completed") and (i.get("date") or "") <= t and i.get("feedback_status") != "Complete"),
            "upcoming": [{"date": i["date"], "time": i.get("start_time"), "candidate": clip(i.get("candidate_name"), 60), "requisition": clip(i.get("requisition_title")),
                          "round": f"Round {i.get('round_number')} · {clip(i.get('round_name'), 40)}", "interviewers": [clip(x, 40) for x in i.get("interviewers", []) if x][:4]} for i in upcoming[:MAX_ROWS]],
        }
        if user["role"] == "management" and len(visible) < len(counts):
            snap["interviews"]["note"] = "Totals cover all interviews for these requirements; details are shown only for interviews you are assigned to."
    else:
        missing.append("interviews")

    if can(user, "offer.view"):
        offers = [o for o in await list_offers(user, {}) if o.get("requisition_id") in rids]
        latest = {}
        for o in sorted(offers, key=lambda o: o.get("created_at") or ""):
            latest[o["application_id"]] = o
        cur = list(latest.values())
        snap["offers"] = {"offer_records": len(offers), "applications_with_offers": len(cur),
                          "current_offer_status": dict(Counter(o["status"] for o in cur)),
                          "released_awaiting_response": sum(1 for o in cur if o["status"] == "Released"),
                          "awaiting_approval": sum(1 for o in cur if o["status"] == "Approval Pending"),
                          "accepted": sum(1 for o in cur if o["status"] == "Accepted"),
                          "recent": [{"candidate": clip(o.get("candidate_name"), 60), "requisition": clip(o.get("requisition_title")), "status": o["status"],
                                      "released": o.get("release_date"), "accepted": o.get("accepted_date"), "valid_until": o.get("validity_date")}
                                     for o in sorted(cur, key=lambda o: o.get("updated_at") or "", reverse=True)[:MAX_ROWS]],
                          "note": "Status is the latest offer per application (earlier declined/expired offers replaced by a re-offer are not double counted)."}
    else:
        missing.append("offers")

    if can(user, "joining.view"):
        js = [j for j in await list_joinings(user, {}) if j.get("requisition_id") in rids]
        snap["joinings"] = {"by_status": dict(Counter(j.get("status") for j in js)),
                            "expected": [{"candidate": clip(j.get("candidate_name"), 60), "requisition": clip(j.get("requisition_title")), "status": j.get("status"),
                                          "tentative_date": j.get("tentative_date"), "confirmed_date": j.get("confirmed_date")}
                                         for j in js if j.get("status") not in ("Joined", "No Show", "Cancelled")][:MAX_ROWS]}
    else:
        missing.append("joining")

    if "metrics" in focus:
        snap["metrics"] = await metrics_for(user, reqs if any_filter else None)
    snap["permissions_note"] = missing
    return snap, reqs, missing


async def metrics_for(user, reqs=None):
    """Cost / Age per Hire exactly as the Analytics module calculates them (filtered to the matched requisitions)."""
    if not can(user, "analytics.view"):
        return {"unavailable": "Your role cannot view recruitment analytics."}
    a = await compute(user, {})
    codes = {r.get("code") for r in reqs} if reqs is not None else None
    hires = [h for h in a["aph"]["hires"] if codes is None or h.get("requisition_code") in codes]
    days = [h["days"] for h in hires if h.get("days") is not None]
    out = {"age_per_hire": {"definition": "Actual date of joining − CRF raised date (calendar days)",
                            "formulas": [r"\text{Age per Hire (days)} = \text{Actual Joining Date} - \text{CRF Raised Date}",
                                         r"\text{Average Age per Hire} = \frac{\sum \text{Age per Hire}}{\text{Hires with valid dates}}"],
                            "hires_with_value": len(days),
                            "average_days": round(sum(days) / len(days), 1) if days else None, "min_days": min(days) if days else None, "max_days": max(days) if days else None,
                            "hires_missing_or_invalid_dates": len(hires) - len(days)}}
    if can(user, "cost.view") and a.get("cost"):
        hc = [h for h in a["cost"]["hire_costs"] if codes is None or h.get("requisition_code") in codes]
        done = [h["total"] for h in hc if h.get("total") is not None]
        out["cost_per_hire"] = {"definition": "Candidate annual CTC + consulting fees + recruiter fees (₹ lakhs); average over joined hires with confirmed cost",
                                "formulas": [r"\text{Cost per Hire} = \text{Candidate Annual CTC} + \text{Consulting Fees} + \text{Recruiter Fees}",
                                             r"\text{Average Cost per Hire} = \frac{\sum \text{Cost per Hire}}{\text{Joined hires with confirmed cost}}"],
                                "joined_hires": len(hc), "hires_with_confirmed_cost": len(done),
                                "average_lakhs": round(sum(done) / len(done), 2) if done else None, "total_lakhs": round(sum(done), 2) if done else None}
    return out


async def candidate_lookup(user, name: str):
    if not can(user, "cand.view") or not name:
        return {"unavailable": "No candidate name given." if name else "Your role cannot view candidates."}
    q = name.lower().strip()
    cands = [c for c in await list_candidates(user, {}) if q in (c.get("name") or "").lower()][:5]
    out = {"query": clip(name, 60), "matches": len(cands), "candidates": [], "retrieved_at": now_iso()}
    apps = await list_applications(user, {}) if can(user, "app.view") else []
    for c in cands:
        row = {"code": c.get("code"), "name": clip(c.get("name"), 60), "source": clip(c.get("source"), 40)}
        if can(user, "app.view"):
            row["applications"] = [{"requisition": a.get("requisition_code"), "role": clip(a.get("requisition_title")), "stage": a["status"],
                                    "days_in_stage": a.get("days_in_stage"), "recruiter": clip(a.get("recruiter"), 50)}
                                   for a in apps if a["candidate_id"] == c["id"]]
        out["candidates"].append(row)
    return out
