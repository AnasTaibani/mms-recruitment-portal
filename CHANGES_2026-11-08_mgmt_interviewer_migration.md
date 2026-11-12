# MMS Recruitment Portal — Management as Interviewers & Joined → Screening migration (08-11-2026)

## 1. Management members can also interview

**How it works.** Roles can now be additive. A role can carry another role's capabilities through `ROLE_IMPLIES` in `backend/core.py`. Management implies Interviewer. No user is named or hard-coded. Every Management account gets the Interviewer capability on top of its own:
- Permissions are the union of Management and Interviewer, which adds only `feedback.submit` (Management already had read access). `/auth/me` returns `roles: ["management", "interviewer"]`, and the role label reads "Management + Interviewer".
- On startup and whenever a user is created or edited, each Management user gets an interviewer person record. It carries their designation and role, so they appear in the **Interviewer(s)** list when scheduling, shown as "Name — Designation, Management". If the person later leaves Management, the record is hidden from pick-lists but kept for past interviews. It reappears if the role comes back.
- An `extra_roles` field on a user account is also honoured. It is an optional way to give someone a second role later, and is not used yet.

**What Management can do as an interviewer.** See the interviews they are assigned to and the candidates in them. Open interview details. Submit feedback and scorecards (rating, recommendation = their decision, remarks), once per interview. These appear in the Interviews page (defaults to "assigned to me") and in **Dashboard → My interviews**.

**What they still cannot do (enforced on the server).**
- Create or edit requisitions or candidate master records.
- Move candidates, record screening or shortlisting, schedule interviews or change interview status, or record selections.
- Create, approve or release offers, or change costs or hire-cost confirmations.
- Mark candidates Joined, or change settings.
- Give feedback on interviews they are not on.

**Unassigned interviews.** By default Management can open only the interviews they are assigned to. Dashboards, analytics and reports still show organisation-wide interview counts. A Super Admin can allow read-only access to all interviews: Settings → General → "Management can view all interviews". This is the "separately authorised" case, and even then they cannot give feedback on interviews they are not part of.

**Both experiences.** Management users see a switch on the Dashboard: **Management overview | My interviews**. Their navigation is unchanged.

Files: `core.py` (effective roles, permissions, interview scope), `routes_admin.py` (person records, setting), `server.py` (startup sync), `routes_analytics.py` (org-wide interview counts), `components/common/FormDialog.jsx` (designation in the interviewer list), `pages/Dashboard.jsx`, `pages/Interviews.jsx`, `pages/Settings.jsx`, `components/AppActions.jsx`, `tests/test_mgmt_interviewer.py`.

## 2. One-time migration: every application in Joined → Screening

**I have not run it against production.** This environment cannot reach your database, and the brief says to verify the preview first. You run it, in either of the two ways below.

**What it changes.** For each application in Joined at the time of the run, it changes only these fields:
- the current status becomes Screening, and the application is no longer closed;
- the stage date is updated;
- one history entry is added: "Joined → Screening", reason "Production candidate status reset", with the migration ID `2026-11-08-joined-to-screening`;
- the migration ID is added to the application's `migrations` list.

Each moved application also gets one Activity Log entry. It holds the candidate ID, application ID, previous status Joined, new status Screening, timestamp, migration ID and reason.

**What it keeps.** Candidates, CVs, requisition mappings, source and partner, interviews and feedback, selections, offers and their history, joining records with their dates, CTC and fees, and all earlier history. Nothing is deleted or recreated. Applications in other stages are not touched.

**Filled positions.** A requisition's filled count now means "applications currently Joined that have a joining record". So after the migration, filled positions and open positions on the dashboard reflect the new status. The joining records themselves stay as history. Requisition status (for example Closed) is not changed, and the preview lists any closed requisitions involved.

**Safety built in.**
1. **Backup:** the full documents of the affected applications, plus the requisitions' filled counts, are saved to `migration_backups` before anything changes. The CLI can also write a JSON file with `--backup-file`.
2. **Preview:** shows the environment, database, host, total applications by status, the exact list of applications that would move, and the count.
3. **Count check:** the run requires the previewed count. If the data changed since the preview, it refuses.
4. **Confirmation:** the confirmation phrase `MOVE JOINED TO SCREENING` plus the database name, typed in.
5. **Transaction:** the change runs in a MongoDB transaction on Atlas (a replica set). On a standalone server each update is guarded, so it can be safely re-run.
6. **Verification:** checks that every target is now in Screening, that the application count is unchanged, that a fingerprint of all *other* applications is unchanged, and that related records and costs are still there.
7. **Re-running:** once completed, running it again changes nothing and adds no audit entries.
8. **Rollback:** `python scripts/migrate_joined_to_screening.py --rollback --database <DB>` restores the moved applications to Joined from the backup.

**How to run it in production.** First take an Atlas snapshot: Atlas → your cluster → Backup → Take snapshot now. Then use either:
- **In the portal (no shell needed):** deploy this version and sign in as Super Admin. Go to Master Data & Settings → Data cleanup → **Status migration: Joined → Screening**. Check the environment, database name and the list of applications. Type the phrase and the database name, then click **Move N to Screening**. The result panel shows the verification.
- **From your Mac:** in the `backend` folder with `.env` pointing at Atlas, run `python scripts/migrate_joined_to_screening.py` to preview. Then run `python scripts/migrate_joined_to_screening.py --execute --database <DB_NAME> --expect <N> --backup-file joined_backup.json`.

Files: `backend/data_migrations.py` (new), `backend/scripts/migrate_joined_to_screening.py` (new), `routes_admin.py` (preview/run endpoints, Super Admin only), `core.py` (`recount_filled`), `pages/Settings.jsx` (migration card), `tests/test_status_migration.py` (new).

## 3. Test results (local test databases only)
- `test_mgmt_interviewer.py`, 9 passed: Management dashboard, analytics and reports work. A Management user is selectable as an interviewer, shown with their designation. They see only their assigned interviews, with organisation-wide counts on the dashboard. They can submit feedback, but not twice, not on an unassigned interview, and not as a Management member who is off the panel. Restrictions (requisitions, candidate edits, pipeline moves, screening, interview status, selection, offers, costs, hire cost, settings) all refused. The "view all interviews" setting works. Interviewer and Recruiter permissions are unchanged. The interviewer record is hidden and restored when the role changes.
- `test_status_migration.py`, 8 passed, on a standalone server and on a replica set (transactional). Covered: preview lists exactly the Joined applications; a wrong phrase, wrong database or stale count is refused. The run verified; every moved application is in Screening with its old history intact plus one new entry. Candidate, offer (Accepted + history), joining (Joined + date), selection and cost records are unchanged. Other applications are byte-for-byte identical. One audit entry per application holds all required fields. Analytics show 0 Joined, Screening increased, funnel and cost per hire updated, and filled positions back to 0. A re-run is a no-op with no new audit entries. New candidates can still join normally afterwards. The CLI preview and rollback also worked.
- Earlier suites, `test_hire_cost.py` and `test_workflow.py`, still pass (30). With the 9 Management tests above, that is 39 in one run; the migration tests are skipped in a normal run because they need a throw-away database.
- Browser: scheduled an interview with a Management member, who showed as "Name — Director, Delivery, Management". Logged in as that member: the dashboard switch showed My interviews, the Interviews page listed only their interview, and they submitted a scorecard. They had no stage or "Mark completed" actions and no candidate edit. The migration card showed the preview, with the run button locked until both confirmations were typed. No JS errors.

## 4. Things to know
- After the migration, these applications sit in Screening with all their later records still in place: offer accepted, joining done, cost confirmed. If someone moves one forward again, the stage wizard will find those records already complete.
- Running it a second time later will not move applications that join after the first run. That is by design: the migration is one-time.
