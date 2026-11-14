"""One-time correction: credit each application to the candidate's recruiter.

Until 14 Nov 2026 a new application took the REQUISITION's recruiter, so Recruiter performance credited everyone on a
requisition to its owner. This sets each application's recruiter to the candidate's recruiter (as shown on the
Candidates page), for open AND closed applications, so past hires are credited correctly too.
Applications whose candidate has no recruiter are left as they are. Nothing else is changed.

Usage (from the backend folder, with backend/.env pointing at the database):
    python scripts/fix_application_recruiters.py                                    # preview only
    python scripts/fix_application_recruiters.py --execute --database <DB_NAME> --expect <N> --backup-dir ~/mms-backups
    python scripts/fix_application_recruiters.py --restore <backup file> --database <DB_NAME>
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from core import db, client  # noqa: E402


async def plan():
    names = {m["id"]: m["name"] async for m in db.masters.find({"type": "recruiter"}, {"_id": 0, "id": 1, "name": 1})}
    cands = {c["id"]: c async for c in db.candidates.find({}, {"_id": 0, "id": 1, "code": 1, "name": 1, "recruiter_id": 1})}
    changes = []
    async for a in db.applications.find({}, {"_id": 0, "id": 1, "code": 1, "candidate_id": 1, "recruiter_id": 1, "status": 1}):
        c = cands.get(a["candidate_id"]) or {}
        want = c.get("recruiter_id")
        if want and want != a.get("recruiter_id"):
            changes.append({"id": a["id"], "code": a["code"], "candidate": c.get("name"), "status": a["status"],
                            "old": a.get("recruiter_id"), "new": want,
                            "old_name": names.get(a.get("recruiter_id"), "(none)"), "new_name": names.get(want, "?")})
    return changes


def show(changes):
    print(f"Database: {db.name}\n")
    if not changes:
        print("Every application already matches its candidate's recruiter. Nothing to change.")
        return
    print(f"{'Application':<12} {'Candidate':<24} {'Stage':<20} Recruiter")
    for c in changes:
        print(f"{c['code']:<12} {(c['candidate'] or '')[:23]:<24} {c['status'][:19]:<20} {c['old_name']} -> {c['new_name']}")
    print(f"\napplications to update: {len(changes)}")


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--restore")
    ap.add_argument("--database")
    ap.add_argument("--expect", type=int)
    ap.add_argument("--backup-dir")
    a = ap.parse_args()
    try:
        if a.restore:
            data = json.loads(Path(a.restore).read_text())
            if a.database != db.name or data["database"] != db.name:
                raise SystemExit(f"--database / backup database / connected database must all match ('{db.name}'). Nothing was done.")
            for c in data["changes"]:
                await db.applications.update_one({"id": c["id"], "recruiter_id": c["new"]}, {"$set": {"recruiter_id": c["old"]}})
            print(f"Restored the previous recruiter on {len(data['changes'])} application(s).")
            return
        changes = await plan()
        show(changes)
        if not a.execute:
            if changes:
                print(f"\nPreview only - nothing changed. To apply:\n  python scripts/fix_application_recruiters.py --execute "
                      f"--database {db.name} --expect {len(changes)} --backup-dir ~/mms-backups")
            return
        if a.database != db.name:
            raise SystemExit(f"\n--database '{a.database}' does not match '{db.name}'. Nothing was done.")
        if a.expect != len(changes):
            raise SystemExit(f"\n--expect {a.expect} does not match the {len(changes)} changes found now. Preview again. Nothing was done.")
        if not changes:
            return
        if not a.backup_dir:
            raise SystemExit("\n--backup-dir is required. Nothing was done.")
        folder = Path(a.backup_dir).expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        f = folder / f"{db.name}_app_recruiters_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        f.write_text(json.dumps({"database": db.name, "taken_at": datetime.now(timezone.utc).isoformat(), "changes": changes}, indent=1))
        if len(json.loads(f.read_text())["changes"]) != len(changes):
            raise SystemExit("Backup check failed. Nothing was changed.")
        for c in changes:
            await db.applications.update_one({"id": c["id"]}, {"$set": {"recruiter_id": c["new"]}})
        left = await plan()
        await db.activity.insert_one({"id": f"fixrec-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}", "at": datetime.now(timezone.utc).isoformat(),
                                      "user_id": None, "user_name": "System (recruiter correction script)", "action": "data_correction",
                                      "entity": "application", "entity_id": None, "label": "Applications credited to candidate's recruiter",
                                      "detail": f"{len(changes)} application(s) updated. Backup: {f.name}"})
        print(f"\nBackup: {f}\nUpdated {len(changes)} application(s)." + ("" if not left else f" WARNING: {len(left)} still differ - check them."))
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
