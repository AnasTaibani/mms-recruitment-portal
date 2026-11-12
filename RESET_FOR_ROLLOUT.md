# Reset production for a fresh rollout

Script: `backend/scripts/reset_for_rollout.py`

| Deleted | Kept |
|---|---|
| Candidates, requisitions, applications, screening/shortlisting reviews, interviews, feedback, selections, offers, joinings, cost & invoice entries, uploaded-file records, import batches, activity log, notifications, login attempts, old migration backups, record-number counters | Users and their roles, all setup lists (departments, job titles, locations, sources, partners, recruiters, interviewers, hiring managers, round types, rejection reasons, priorities, employment types), portal settings, the "Joined → Screening migration already ran" marker |

Numbering restarts: first records become REQ-0001, CAN-00001, APP-00001, INT-0001, OFF-0001, JN-0001, CST-0001.
One activity-log entry records the reset.

## Steps (on your Mac)

1. Ask everyone to stop using the portal for ~10 minutes.
2. `cd mms-portal-updated/backend` — `backend/.env` must contain the production `MONGO_URL` and `DB_NAME`.
3. Preview (changes nothing):
   ```
   python3 scripts/reset_for_rollout.py
   ```
   Check **Database** and **Mongo host** are production, and the counts look right. It prints the exact command for step 4.
4. Run the command it printed, e.g.:
   ```
   python3 scripts/reset_for_rollout.py --execute --database <DB_NAME> --expect <N> --backup-dir ~/mms-backups
   ```
   It writes a full backup first, checks it, then deletes. If anything changed since the preview, or the database name is wrong, it stops without deleting.
5. Sign in to the portal: dashboard shows zeros, Users and Settings → Masters are unchanged.

## If you need the data back

```
python3 scripts/reset_for_rollout.py --restore ~/mms-backups/<DB_NAME>_<date_time> --database <DB_NAME>
```
Only works while the recruitment collections are still empty, so old and new records are never mixed.

## Notes
- The backup folder contains candidate personal data. Keep it somewhere private and delete it once you're sure you don't need it.
- Uploaded resume files are stored in Emergent's file storage, not in MongoDB. The script removes their records, so they can no longer be opened from the portal, but the files themselves stay in that storage.
- Tested on a local copy of the test database (11,000 records): wrong count / wrong database / no backup folder all refused; reset deleted only the listed collections; users, setup lists and settings unchanged; portal sign-in, empty dashboard and new numbering worked; restore refused while new data existed and fully restored once empty. It was not run against production.
