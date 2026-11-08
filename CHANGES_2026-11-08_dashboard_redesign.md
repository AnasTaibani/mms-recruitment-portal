# MMS Recruitment Portal — Bento dashboard & neutral palette (08-11-2026)

## What changed
**Palette (whole app shell; login page unchanged).** Blue (#1E63CE family) was replaced with matte black #18181B, off-white #F8F7F5 background, white cards and warm greys. The brand logo is kept. Colour is used only for outcomes: muted green (positive / joined), muted red (negative), ochre (pending / warning). Offer-stage badges changed from purple to stone. The login page keeps its own blue look through a scoped `.login-theme` class.

**Dashboard (`/`), rebuilt as a bento grid.** 4 columns on desktop, 2 on tablet, 1 on phone, with no horizontal scroll.
- **Filters:** period pills (7D / 30D / 90D / Quarter / Year / Custom with dates), department, recruiter, requisition, and an Export menu (summary, funnel, recruiters, sources, cost per hire, age per hire).
- **Hero:** greeting, the selected period and the comparison period. A large black "Hires in period" card, plus Total candidates, Open requisitions, In screening, In interview, Offers released and Offers accepted. Numbers count up on load and every card links to its filtered list. A change % appears only when the previous period has data; otherwise it shows "—".
- **Recruitment performance:** an area chart of candidates added, shortlisted, interviews completed, offers released and joined. Weekly / monthly toggle, a hover tooltip with dated values, and click-to-hide series.
- **Funnel:** New → Screening → Shortlisted → Interview → Selected → Offer Released → Offer Accepted → Joined. Shows counts, % of the previous stage, drop-off and overall conversion. Clicking a stage opens the Pipeline filtered to it.
- **Cost per hire:** average cost per hire, total cost, and the CTC / consulting / recruiter split. A trend line appears once two or more periods have confirmed costs. Hires without confirmed costs, and accepted offers awaiting cost, are flagged.
- **Age per hire:** average, fastest and longest (DOJ − CRF date). Trend, longest requisitions, and missing CRF dates are flagged.
- **Sources:** segmented bar plus a table. Clicking a source opens Candidates filtered to it.
- **Recruiter performance:** comparison chart by assigned, screened, interviews, offers or joined (pill switch), plus a table with age and cost per hire. No scores are invented.
- **Requisitions:** open, positions approved, filled, remaining, on hold and average time to fill. Also an ageing bar (0–30 / 31–60 / 61–90 / 90+ days / no CRF) and the oldest open requisitions. It has its own hiring-manager, location and status filters.
- **Operations:** upcoming interviews (today highlighted), pending actions (each one clickable), recent activity with user and time, and the current pipeline distribution (clickable).
- **Interviewers** keep their own home (upcoming interviews and pending feedback). **Management** keeps the Management overview / My interviews switch.

**Analytics, Costs and the other pages** pick up the same card and number style through the shared components (`Kpi`, `Section`, `PageHeader`) and the neutral chart palette.

**Drill-down.** Pipeline, Candidates, Offers, Requisitions and Interviews now read filters from the URL (e.g. `/pipeline?status=Screening`). `/applications` accepts a comma-separated `status`.

## Data
New `GET /api/dashboard` (needs `analytics.view`) aggregates everything on the server from records the user can access. It reuses the Analytics module for cost, age-per-hire, sources and recruiters, so the dashboard, Analytics page and exports agree.
- **Event dates:** candidates added = first application date; screening / shortlisted / interview = first entry into that stage in the stage history; interviews completed = interview date; offers released / accepted = first release / acceptance per application; joined = actual joining date of applications currently Joined.
- **Previous period:** the period of equal length immediately before.
- **Funnel:** applications created in the period.
- **Time to fill:** last joining − CRF date, for fully filled requisitions.

## Tech notes
The portal is React 19 (Create React App) in JavaScript with Tailwind, shadcn/ui and recharts. It was not converted to TypeScript or Next.js. The Web3 component file was not added. Its layout and interaction ideas were rebuilt in `src/components/bento.jsx` (tile, pills, count-up, delta, segmented bar, tooltip) with no new dependencies.

Files: `backend/routes_dashboard.py` (new), `backend/server.py`, `backend/routes_recruit.py`, `backend/tests/test_dashboard.py` (new); `frontend/src/components/bento.jsx` (new), `src/components/analytics/shared.jsx` (moved from Dashboard), `src/lib/urlFilters.js` (new), `src/pages/Dashboard.jsx` (rewritten), `src/index.css`, `src/components/common/Page.jsx`, `src/components/common/StatusBadge.jsx`, `src/pages/{Pipeline,Candidates,Offers,Requisitions,Interviews,Analytics,Login}.jsx` and colour-only changes in a few other components.

## Tests
- `test_dashboard.py`, 5 passed: figures match the records; there are no invented comparisons; it is consistent with `/api/analytics` (cost, age per hire, sources, recruiters); period arithmetic and validation work; roles behave as expected (Interviewer 403, Management sees the org view and only their own interviews, Recruiter full).
- Earlier suites still pass, 44 tests in total.
- Browser at 1440 / 820 / 390 px: no horizontal overflow and no JS errors. Period, granularity and custom range all update the figures, the tooltip shows dated values, and funnel, source and pending clicks open filtered lists.
