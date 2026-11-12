"""Reset the portal for a fresh rollout: delete all recruitment data, keep users, roles, setup lists and settings.

DELETED  candidates, requisitions, applications, stage reviews, interviews, interview feedback, selections, offers,
         joinings, cost / invoice entries, uploaded-file records, import batches, the activity log, notifications,
         login-attempt records, earlier migration backups, and the record-number counters (numbering restarts:
         CAN-00001, REQ-0001, APP-00001, INT-0001, OFF-0001, JN-0001, CST-0001).
KEPT     users (and their roles), setup lists ("masters": departments, job titles, sources, partners, recruiters,
         interviewers, ...), portal settings, and the record that the Joined -> Screening migration already ran
         (so it can never be re-run against new data).

Usage (from the backend folder, with backend/.env pointing at the database to reset):
    python scripts/reset_for_rollout.py                                   # preview only - changes nothing
    python scripts/reset_for_rollout.py --execute --database <DB_NAME> --expect <N> --backup-dir <folder>
    python scripts/reset_for_rollout.py --restore <folder> --database <DB_NAME>   # put the backup back

--expect must equal the "records to delete" total shown by the preview; if the data changed in between, nothing is done.
--backup-dir is required: every collection is written to <folder>/<collection>.json (MongoDB Extended JSON) BEFORE
anything is deleted, and the run stops if the backup can't be written or read back.
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from bson import json_util
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from core import db, client  # noqa: E402

WIPE = ["candidates", "requisitions", "applications", "stage_reviews", "interviews", "feedback", "selections", "offers",
        "joinings", "costs", "files", "import_batches", "activity", "notifications", "login_attempts",
        "migration_backups", "counters"]
KEEP = ["users", "masters", "settings", "data_migrations"]


def host():
    import os
    u = urlparse(os.environ["MONGO_URL"])
    return (u.hostname or "?") + (" (local)" if u.hostname in ("localhost", "127.0.0.1") else "")


async def counts(names):
    existing = set(await db.list_collection_names())
    return {c: (await db[c].count_documents({}) if c in existing else 0) for c in names}


async def preview():
    wipe, keep = await counts(WIPE), await counts(KEEP)
    others = sorted(set(await db.list_collection_names()) - set(WIPE) - set(KEEP))
    print(f"Database    : {db.name}\nMongo host  : {host()}\n")
    print("WILL BE DELETED")
    for c, n in wipe.items():
        print(f"  {c:<18} {n:>7}")
    total = sum(wipe.values())
    print(f"  {'records to delete':<18} {total:>7}\n")
    print("WILL BE KEPT")
    for c, n in keep.items():
        print(f"  {c:<18} {n:>7}")
    users = await db.users.find({}, {"_id": 0, "email": 1, "role": 1, "roles": 1}).to_list(10000)
    roles = {}
    for u in users:
        for r in (u.get("roles") or [u.get("role")]):
            roles[r] = roles.get(r, 0) + 1
    print(f"  users by role      {roles}")
    if others:
        print(f"\nNot touched (unknown to the portal): {', '.join(others)}")
    return total, keep


async def backup(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    written = {}
    existing = set(await db.list_collection_names())
    for c in WIPE + KEEP:  # kept collections are backed up too, for a complete snapshot
        docs = await db[c].find({}).to_list(None) if c in existing else []
        p = folder / f"{c}.json"
        p.write_text(json_util.dumps(docs, json_options=json_util.RELAXED_JSON_OPTIONS))
        back = json_util.loads(p.read_text())
        if len(back) != len(docs):
            raise SystemExit(f"Backup check failed for {c}: wrote {len(docs)}, read back {len(back)}. Nothing was deleted.")
        written[c] = len(docs)
    (folder / "_manifest.json").write_text(json.dumps({"database": db.name, "host": host(), "taken_at": datetime.now(timezone.utc).isoformat(),
                                                       "counts": written}, indent=2))
    return written


async def execute(a):
    total, keep_before = await preview()
    if a.database != db.name:
        raise SystemExit(f"\n--database '{a.database}' does not match the connected database '{db.name}'. Nothing was done.")
    if a.expect is None or a.expect != total:
        raise SystemExit(f"\n--expect {a.expect} does not match the {total} records found now. Run the preview again. Nothing was done.")
    if not a.backup_dir:
        raise SystemExit("\n--backup-dir is required. Nothing was done.")
    folder = Path(a.backup_dir) / f"{db.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    written = await backup(folder)
    print(f"\nBackup written and verified: {folder}  ({sum(written.values())} documents)")
    deleted = {}
    for c in WIPE:
        deleted[c] = (await db[c].delete_many({})).deleted_count
    remaining = {c: n for c, n in (await counts(WIPE)).items() if n}
    keep_after = await counts(KEEP)
    if remaining or keep_after != keep_before:
        print(f"\nWARNING - check needed. Remaining: {remaining}  Kept before: {keep_before}  after: {keep_after}")
        print(f"The backup in {folder} can be restored with --restore.")
        raise SystemExit(1)
    await db.activity.insert_one({"id": f"reset-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}", "at": datetime.now(timezone.utc).isoformat(),
                                  "user_id": None, "user_name": "System (rollout reset script)", "action": "rollout_reset",
                                  "entity": "system", "entity_id": None, "label": "Data reset for fresh rollout",
                                  "detail": f"Deleted {sum(deleted.values())} records; users, setup lists and settings kept. Backup: {folder.name}"})
    print(f"\nDone. Deleted {sum(deleted.values())} records: {deleted}")
    print(f"Kept unchanged: {keep_after}")
    print("Record numbering restarts at 1. Keep the backup folder somewhere safe (it contains candidate personal data).")


async def restore(a):
    folder = Path(a.restore)
    man = json.loads((folder / "_manifest.json").read_text())
    if a.database != db.name or man["database"] != db.name:
        raise SystemExit(f"--database / backup database / connected database must all match ('{db.name}'). Nothing was done.")
    busy = {c: n for c, n in (await counts(WIPE)).items() if n and c not in ("activity", "login_attempts")}
    if busy:
        raise SystemExit(f"These collections already have data, so restoring would mix old and new records: {busy}. Nothing was done.")
    await db.activity.delete_many({"action": "rollout_reset"})
    restored = {}
    for c in WIPE:
        docs = json_util.loads((folder / f"{c}.json").read_text())
        if c == "login_attempts":
            continue  # not worth bringing back
        if docs:
            await db[c].insert_many(docs)
        restored[c] = len(docs)
    print(f"Restored from {folder}: {restored}")


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
            await restore(a)
        elif a.execute:
            await execute(a)
        else:
            total, _ = await preview()
            print(f"\nPreview only - nothing changed. To delete, run:\n  python scripts/reset_for_rollout.py --execute --database {db.name} --expect {total} --backup-dir ~/mms-backups")
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
