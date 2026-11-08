"""One-time production migration: move every application currently in Joined back to Screening.

Only the application status changes. Candidates, requisition mappings, interviews and feedback, offers, joining records and
dates, CTC / consulting / recruiter fees and all earlier history are kept. The affected applications are backed up
first (collection `migration_backups`, plus a JSON file with --backup-file).

Usage (from the backend folder, with backend/.env pointing at the database to change):
    python scripts/migrate_joined_to_screening.py                                   # preview only — changes nothing
    python scripts/migrate_joined_to_screening.py --execute --database <DB_NAME> --expect <N> [--backup-file backup.json]
    python scripts/migrate_joined_to_screening.py --rollback --database <DB_NAME>  # put them back to Joined from the backup
--expect must equal the count shown by the preview; if the data changed in between, nothing is done.
Re-running after it has completed changes nothing.
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from core import db, client  # noqa: E402
import data_migrations as dm  # noqa: E402


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--rollback", action="store_true")
    ap.add_argument("--database")
    ap.add_argument("--expect", type=int)
    ap.add_argument("--backup-file")
    a = ap.parse_args()
    p = await dm.preview()
    print(f"Environment : {p['environment']}\nDatabase    : {p['database']}\nMongo host  : {p['mongo_host']}\nMigration   : {p['migration_id']} — {p['reason']}\n")
    print(f"Applications in the database: {p['total_applications']}  by status: {p['by_status']}")
    print(f"Applications currently Joined (would move to Screening): {p['count']}")
    for r in p["applications"]:
        print(f"  {r['application_code']:<10} {r['candidate_code'] or '':<10} {(r['candidate'] or '')[:30]:<30} {r['requisition_code'] or '':<9} "
              f"req {r['requisition_status'] or '':<8} DOJ {r['actual_join_date'] or '—':<10} cost {'yes' if r['has_cost'] else 'no'}")
    if p["closed_requisitions_affected"]:
        print(f"Note: some belong to closed / filled requisitions: {', '.join(p['closed_requisitions_affected'])} (requisition status is not changed)")
    if p["already_applied"]:
        print(f"\nAlready completed on {p['last_run'].get('completed_at')} — nothing to do.")
    if not (a.execute or a.rollback):
        if not p["already_applied"]:
            print(f"\nPreview only — nothing changed. To run: --execute --database {p['database']} --expect {p['count']} --backup-file joined_backup.json")
        return
    if a.database != p["database"]:
        sys.exit(f"Refusing: --database '{a.database}' does not match the connected database '{p['database']}'.")
    if input(f"\nType the database name '{p['database']}' again to continue: ").strip() != p["database"]:
        sys.exit("Aborted.")
    if a.rollback:
        print(await dm.rollback("Migration script"))
        return
    if a.backup_file:
        docs = await db.applications.find({"status": "Joined"}, {"_id": 0}).to_list(100000)
        Path(a.backup_file).write_text(json.dumps(docs, indent=1, default=str))
        print(f"Backup file written: {a.backup_file} ({len(docs)} applications)")
    try:
        out = await dm.run("Migration script", None, a.expect)
    except ValueError as e:
        sys.exit(f"Refusing: {e}")
    print(json.dumps(out, indent=1, default=str))
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
