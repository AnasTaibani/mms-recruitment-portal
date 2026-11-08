# MMS Recruitment Portal — Workflow correction (08-11-2026)

> **Note:** the cost rules below (fees-only Cost per Hire, cost not blocking joining) were replaced the same day — see `CHANGES_2026-11-08_cost_per_hire.md`.

Applies the "Workflow Audit & Correction" brief. No redesign, no data deleted, no accounts changed.

## 1. Modified / new files
**Backend**
- `backend/workflow.py` *(new)* — the shared validation service: transition matrix, stage prerequisites, readiness report, legacy handling.
- `backend/core.py` — `set_app_status()` is the single gate for every stage change (matrix, reasons, prerequisites, overrides, audit).
- `backend/routes_recruit.py` — `move_application()`, new readiness / stage-review / interview-waiver / cost-status endpoints, `interview_rounds_required` on requisitions, cost check before requisition closure.
- `backend/routes_interviews.py` — feedback & completion rules, stage sync, pending-feedback list.
- `backend/routes_offers.py` — selection validation, offer / re-offer integrity, joining integrity, cost linking and reconciliation.
- `backend/routes_analytics.py` — Cost per Hire = fees ÷ joined (CTC removed), reconciliation counts, cycle-time label.
- `backend/routes_admin.py` — `/meta` exposes the matrix; settings can only narrow it.
- `backend/routes_import.py` — imported applications are marked as historical (legacy) records.
- `backend/server.py` — one-time migration; offer expiry updates the application.
- `backend/tests/test_workflow.py` *(new)* — regression suite for the 13 scenarios (+4 extra checks).
- `backend/tests/test_mms_e2e.py`, `test_mms_rbac_extra.py` — login uses the Bearer token and the 4 current roles (see limitations).

**Frontend**
- `src/components/StageWizard.jsx` *(new)* — the guided stage-completion wizard.
- `src/components/forms.jsx` — `MoveDialog` (wizard for pipeline stages, reason dialog for outcomes), stricter `SelectionDialog`, rounds field on requisitions.
- `src/components/AppActions.jsx` — re-offer, cost reconciliation entry, offer outcomes only via the offer.
- `src/pages/Pipeline.jsx` — drag-and-drop opens the wizard / reason dialog instead of posting the status.
- `src/pages/Interviews.jsx` — Super Admin "complete without all feedback" with reason; recommendation only after completion.
- `src/pages/CandidateDetail.jsx` — cost status, interview waiver and exceptions shown on each application.
- `src/pages/Costs.jsx`, `Analytics.jsx`, `Dashboard.jsx` — fees-only Cost per Hire, reconciliation KPIs, cycle time labelled separately.
- `src/pages/Settings.jsx` — transitions editor limited to the defined matrix.
- `src/lib/api.js` — shows which stages are missing in error messages.

## 2. Corrected workflows
- **Guided completion.** Choosing a later stage (menu or drag-and-drop) opens the wizard: candidate, application ID, current → requested stage, completed / missing prerequisites, progress bar, form per stage, Back / Next / Cancel, summary and confirmation. Each stage is saved as its own record straight away, so closing the wizard loses nothing.
- **Records created by the wizard:** Screening and Shortlisting reviews (`stage_reviews`: date, owner/reviewer, decision, remarks), interviews and feedback (`interviews`, `feedback`), selection (`selections`), offer and its approval / release / acceptance (`offers`), cost entries (`costs`) or a reconciliation status, joining (`joinings`). The application status is never set to a later stage without these.
- **Backend enforcement.** Every route that changes a stage goes through `set_app_status()` → `workflow.py`. A direct API call is checked exactly like the wizard.
- **Interviews.** The requisition sets how many rounds are needed (`interview_rounds_required`, no upper limit, default 1). A round counts only when every assigned interviewer has given feedback (or a Super Admin completed it with a reason). No feedback on cancelled / no-show interviews; one feedback per interviewer; a final recommendation is needed and can only be set on a completed round. Super Admin can waive interviews with a reason.
- **Selection.** Needs the interview process (or an audited waiver), date (not in the future), decision maker, decision, compensation and approval status; remarks for reject / hold; only one active selection.
- **Offer.** Needs an active selection; one active offer at a time; Submitted → Offer Approval Pending, Released → Offer Released, Accepted → Offer Accepted (acceptance not before release); approval rejection returns the application to Selected; decline / revoke only through the offer. Re-offers record which offer they replace. Expired offers are marked Expired, the recruiter and admins are notified, and the application returns to Selected for a re-offer.
- **Joining.** Joining record only after an accepted offer; Joined only with an accepted offer, an existing joining record and an actual date (not in the future, not before acceptance). Nothing is auto-created. Checklist status is stored on the joining.
- **Costs.** Amount and invoice are optional until known; costs link to candidate and requisition (requisition inferred where unambiguous). Application cost status: Cost Recorded / Invoice Pending / No Recruitment Cost, set automatically from cost records or manually. It does not block joining; it is required before a requisition can be closed.
- **Cost per Hire** = (recruiter fees + recruitment partner / consultancy fees) ÷ candidates joined; CTC excluded; N/A with no joiners; the same filters apply to both. CTC on a cost entry is only used to work out a % fee.
- **Age per Hire** unchanged (Actual DOJ − CRF Raised Date; missing CRF flagged). The initiation-based "cycle time" is labelled as a separate metric.

## 3. Transition matrix (ordinary moves)
Forward moves into later pipeline stages are allowed **only when every earlier stage has its record** (the wizard collects them).

| From | Allowed to |
|---|---|
| New | any later pipeline stage, CV Rejected, On Hold, Candidate Withdrawn |
| Screening | any later pipeline stage, CV Rejected, On Hold, Candidate Withdrawn |
| Shortlisted | any later pipeline stage, CV Rejected, On Hold, Candidate Withdrawn |
| Interview Scheduled / In Progress | any later pipeline stage, Interview Rejected, On Hold, Candidate Withdrawn, No Show |
| Interview Completed | any later pipeline stage, back to Interview Scheduled (extra round), Interview Rejected, On Hold, Candidate Withdrawn |
| Selected | Offer stages, Joined, On Hold, Candidate Withdrawn |
| Offer Approval Pending | Offer Released, Offer Accepted, Joined, On Hold, Candidate Withdrawn, (Offer Revoked\*) |
| Offer Released | Offer Accepted, Joined, Candidate Withdrawn, (Offer Declined\*, Offer Revoked\*) |
| Offer Accepted | Joined, Candidate Withdrawn, No Show, (Offer Revoked\*) |
| On Hold | back to any stage up to the one it was held at, CV Rejected, Candidate Withdrawn |
| Offer Declined / Offer Revoked | Candidate Withdrawn; a re-offer re-opens the offer stage |
| Joined, CV Rejected, Interview Rejected, Candidate Withdrawn, No Show | closed |

\* only through the offer's Decline / Revoke action. Every terminal outcome needs a reason. Super Admin exceptions need a reason, are logged as `[EXCEPTION]`, and can never create Selected / Offer / Joined without their records. The Settings matrix can switch paths off but cannot add paths.

## 4. Database changes & migration
No collection is dropped and no record is deleted or re-statused. Runs automatically once on the next backend start (guarded by `settings.workflow_version = 1`):
- Existing applications get `legacy_stage_index` = furthest stage they had reached, so their earlier stages count as historical records (nothing is back-filled or invented). Their **next** stages follow the new rules.
- `settings.transitions` is replaced by the defined matrix; the old value is kept in `settings.previous_transitions`.

New fields / collection: `stage_reviews` collection; on applications `legacy_stage_index`, `interview_waiver`, `cost_status`, `cost_note`, `cost_status_by/at`, history entries gain `by_id`, `override`, `override_reason`, `records`; on interviews `feedback_override`; on selections `active`, `override`; on offers `replaces`; on joinings `checklist_status`; on requisitions `interview_rounds_required`.

**Before the first deploy:** take an Atlas snapshot/backup (recommended practice; the migration only adds fields).

## 5. Test results (local MongoDB copy, never production)
`backend/tests/test_workflow.py` — **17 passed**:
1 full progression New → Joined ✔ · 2 Screening → Joined blocked, nothing auto-created ✔ · 3 missing feedback blocks completion; override Super Admin only; duplicate / cancelled feedback refused ✔ · 4 selection without interviews refused; Super Admin waiver audited ✔ · 5 Offer Released without a released offer refused (also by override) ✔ · 6 Offer Accepted without acceptance refused; acceptance before release refused ✔ · 7 Joined without accepted offer refused; joining record refused ✔ · 8 joined with invoice pending; amount left blank; status follows the cost record ✔ · 9 No Recruitment Cost ✔ · 9b Cost per Hire fees-only (₹3.3 L ÷ 2 = ₹1.65 L) ✔ · 10 declined offer → re-offer linked; approval rejection back to Selected ✔ · 11 missing CRF flagged; cycle time labelled ✔ · 12 terminal outcomes need reasons; On Hold reactivation; rejected is final ✔ · 13 Interviewer / Management / Recruiter bypass attempts refused; settings cannot widen the matrix ✔ · reports export and audit fields ✔.
Extra direct checks: offer expiry → offer Expired, notifications sent, application back to Selected ✔; migration marks legacy apps, is idempotent, record count unchanged ✔.
Browser (production build behind a Vercel-style proxy): wizard opened from "Move stage → Joined" showed 0/6, recorded screening and shortlisting through its forms, blocked the summary, kept the saves after Cancel, then (after interview / selection / offer) set No Recruitment Cost, took the actual joining date, confirmed and showed the summary; card updated to Joined; terminal move blocked until a reason was typed; Pipeline and Costs pages render; no JS errors.

## 6. Remaining limitations
- `test_mms_e2e.py` and `test_mms_rbac_extra.py` were written for the original 6-role, cookie-only setup (HR Admin / Hiring Manager master records, old free-moving pipeline). Many of their assertions now contradict agreed changes; they need rewriting and were not used as pass/fail evidence. `test_workflow.py` is the suite for this change.
- The wizard reuses the existing Schedule, Feedback, Selection and Offer dialogs; the interview step was exercised in the browser via its buttons' API calls, not by clicking every dialog.
- Existing applications are trusted for stages they had already reached (legacy marker). Their missing historic records are not invented; reports will show them as "Recorded before workflow controls".
- Requisitions that already have joined candidates without a cost status will need one set (Cost Recorded / Invoice Pending / No Recruitment Cost) before they can be closed.
- "Joined" history entries are marked automatic because they are written by the joining record; the user who confirmed it is still recorded.
