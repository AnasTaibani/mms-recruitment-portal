"""Where every application went between two funnel stages.

For each gap (stage -> next stage) the applications that reached the stage but not the next one are split into
  still   - still active at that stage (not a drop-off), and
  exits   - left the process, by the reason already recorded as the application's status.
moved + still + exits == the stage's count, so every application is accounted for.
"""
from collections import Counter

from core import TERMINAL

KIND = {"CV Rejected": "company", "Interview Rejected": "company", "Offer Revoked": "company",
        "Candidate Withdrawn": "candidate", "Offer Declined": "candidate", "No Show": "candidate", "On Hold": "hold"}
KIND_LABEL = {"company": "Company decision", "candidate": "Candidate decision", "hold": "On hold"}

# exit reasons that can happen before an application reaches the next stage (keyed by that stage's pipeline index);
# all are listed (zero counts too) so the user sees what *could* have happened at each step
REASONS_BEFORE = {1: ["CV Rejected", "Candidate Withdrawn", "On Hold"], 2: ["CV Rejected", "Candidate Withdrawn", "On Hold"],
                  3: ["Candidate Withdrawn", "On Hold"], 4: ["Candidate Withdrawn", "On Hold"],
                  6: ["Interview Rejected", "Candidate Withdrawn", "On Hold"], 8: ["Candidate Withdrawn", "On Hold"],
                  9: ["Offer Declined", "Offer Revoked"], 10: ["No Show", "Offer Revoked", "Candidate Withdrawn"]}
STILL_LABEL = {0: "Not screened yet", 1: "Screening in progress", 2: "Waiting for an interview", 3: "Interviews in progress",
               4: "Interviews in progress", 6: "Offer being prepared", 8: "Awaiting the candidate's answer", 9: "Awaiting joining"}


def add_gaps(stages, apps, reached):
    """stages: [{"stage", "count", "_idx"}...] in order; reached(app, k) -> bool for stage k.
    Adds "gap" to every stage but the last, and returns totals for the whole cohort."""
    totals_exit = Counter()
    for k, s in enumerate(stages[:-1]):
        nxt = stages[k + 1]
        pool = [a for a in apps if reached(a, k) and not reached(a, k + 1)]
        still = [a for a in pool if a["status"] not in TERMINAL]
        exits = Counter(a["status"] for a in pool if a["status"] in TERMINAL)
        totals_exit.update(exits)
        names = list(REASONS_BEFORE.get(nxt["_idx"], ["Candidate Withdrawn", "On Hold"]))
        names += [r for r in exits if r not in names]
        s["gap"] = {
            "to": nxt["stage"], "moved": nxt["count"], "still": len(still),
            "still_label": STILL_LABEL.get(s["_idx"], "In progress"),
            "still_statuses": sorted({a["status"] for a in still}),
            "exited": sum(exits.values()),
            "exits": [{"reason": r, "count": exits.get(r, 0), "kind": KIND.get(r, "company")} for r in names],
        }
    for s in stages:
        s.pop("_idx", None)
    joined = stages[-1]["count"] if stages else 0
    exited = sum(totals_exit.values())
    by_kind = Counter()
    for r, n in totals_exit.items():
        by_kind[KIND.get(r, "company")] += n
    return {
        "joined": joined, "exited": exited, "in_progress": len(apps) - joined - exited,
        "by_reason": [{"reason": r, "count": totals_exit.get(r, 0), "kind": KIND[r]} for r in
                      ["CV Rejected", "Interview Rejected", "Candidate Withdrawn", "Offer Declined", "Offer Revoked", "No Show", "On Hold"]],
        "by_kind": [{"kind": k, "label": KIND_LABEL[k], "count": by_kind.get(k, 0)} for k in ("company", "candidate", "hold")],
    }
