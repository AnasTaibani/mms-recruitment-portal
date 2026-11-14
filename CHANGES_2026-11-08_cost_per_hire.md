# MMS Recruitment Portal — Cost per Hire & mandatory cost before joining (08-11-2026)

Supersedes the cost rules in `CHANGES_2026-11-08_workflow.md` (§2 "Costs", "Cost per Hire" and the "cost does not block joining" rule). Everything else in that update stays.

## Formula
- **Cost per Hire (one candidate)** = Candidate annual CTC + Consulting fees + Recruiter fees. Not divided by anything.
  Example: ₹6,00,000 + ₹50,000 + ₹20,000 = **₹6,70,000** (entered as 6 + 0.5 + 0.2 = ₹6.70 L).
- **Average Cost per Hire** = sum of Cost per Hire for joined candidates with confirmed cost ÷ number of those candidates. Same date / department / role / recruiter / partner filters for both.

## What changed
**Joining workflow.** "Recruitment cost" is now a required step in the stage wizard (between Offer and Joining). The user enters annual CTC, consulting fees and recruiter fees (₹ lakhs, INR). The Cost per Hire is shown live in lakhs and rupees, and the user confirms it. Only then can the candidate be marked Joined. CTC is pre-filled from the accepted offer (and fees from any recorded fee entries) as a starting point. The user must check and confirm these values.

**Validation (frontend and backend, same rules).** All three fields are required, and a blank is never read as 0. CTC must be > 0. Fees may be 0. Negatives are refused. Currency must be INR and CTC must be annual. Amounts above ₹1,000 L are refused as "probably typed in rupees". The cost can be confirmed once the offer is accepted.

**No bypass.** Every route to Joined checks for a confirmed cost: the wizard, the move-stage API, the joining record update and pipeline drag-and-drop. A Super Admin override cannot skip it. The joining record is not touched when the check fails.

**Storage and audit.** One cost record per application, kept on the application (`hire_cost`), linked to the candidate and requisition. It holds the three components, the total calculated by the server (any total sent by the browser is ignored), the currency/basis, who confirmed it and when, who last changed it and when, and a version number. A version guard means two people can't overwrite each other's edits. Changes need a reason. Each change is added to `hire_cost_history` with previous and new values, user and timestamp, and is written to the Activity Log.

**Who can change it.** Super Admin and Recruiter (the Recruiter persona includes the former HR Admin role). Management and Interviewers can view it but cannot change it.

**Analytics, dashboard, reports.**
- The Costs page shows average cost per hire, total hiring cost, CTC, consulting + recruiter fees, and hires counted (confirmed / joined). It also has a per-candidate cost table with export. The existing invoice / fee entries table stays below as "Invoices & fee entries".
- The Dashboard KPI, the Analytics cost tab, and the recruiter- and partner-wise cost per hire all use the new formula.
- New **Cost per hire report** (Reports & Export). The monthly / quarterly summary now has "Hires with Confirmed Cost" and Cost per Hire from confirmed costs.
- A requisition with joined candidates cannot be closed until each joined candidate has a confirmed cost.

**Existing data.** Nothing is changed or deleted. Candidates who joined before this rule have no confirmed cost. They are flagged ("not counted as a completed hire") and left out of the average until someone confirms their cost from the application's **Recruitment cost** menu item. Invoice-level cost entries are kept and still editable. Their amounts are no longer the Cost per Hire numerator. The earlier "cost reconciliation status" field is kept on old records but is no longer required.

## Files
Backend: `routes_offers.py` (hire-cost endpoints, validation, joining gate), `workflow.py` (cost step now blocking), `routes_analytics.py` (formula, per-hire list, summary, `cost-per-hire` report), `routes_recruit.py` (closure check, readiness payload), `tests/test_hire_cost.py` (new), `tests/test_workflow.py` (updated for the new rule).
Frontend: `components/HireCost.jsx` (new: entry form with live total, confirmed view, change-with-reason, history), `components/StageWizard.jsx`, `components/AppActions.jsx`, `pages/CandidateDetail.jsx`, `pages/Costs.jsx`, `pages/Analytics.jsx`, `pages/Dashboard.jsx`, `pages/Reports.jsx`.

## Test results (local test database)
`tests/test_hire_cost.py` 15 passed and `tests/test_workflow.py` 17 passed, 30 in total (the zero-fee test runs as 3 cases). Scenarios 1 to 14 of the brief:
1 all positive → ₹6.70 L ✔ · 2 consulting 0 ✔ · 3 recruiter 0 ✔ · 4 both 0 ✔ · 5 CTC blank refused ✔ · 6 consulting blank refused ✔ · 7 recruiter blank refused ✔ · 8 negatives / CTC 0 / USD / monthly CTC / rupee-sized numbers refused ✔ · 9 Joined without cost refused via move, joining record and wizard; joining record left unchanged ✔ · 10 API bypass: override refused, Recruiter blocked without cost, Management/Interviewer cannot write, cost refused before offer acceptance ✔ · 11 Super Admin and Recruiter change with reason; original confirmer kept ✔ · 12 Management / Interviewer changes refused ✔ · 13 history holds Confirmed → Updated → Updated with previous/new values, reason, user, time; 3 activity-log entries ✔ · 14 average = (7.3 + 6.2 + 6.5 + 6.0) ÷ 4 = ₹6.50 L; component totals; report and summary export ✔.
Browser: wizard opened on the cost step with CTC pre-filled. Blank and negative fees showed errors. Live total read ₹6.70 L · ₹6,70,000. After confirming, the wizard moved to joining, and the candidate was marked Joined. A change without a reason was blocked. A change with a reason appeared in the history. The Costs page and Dashboard show the average. No JS errors.

## Limitations
- Historical Excel imports can still create Joined records (it is a data-migration path). Those records show as "cost not confirmed" until someone fills them in.
- Amounts stay in ₹ lakhs like the rest of the portal; the form shows the rupee equivalent beside each field.
