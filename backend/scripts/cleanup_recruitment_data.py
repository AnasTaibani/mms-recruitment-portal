"""Delete all test / demo recruitment data from the connected MongoDB database.

Preserves: users (except TEST_ / @mms.test accounts), the Super Admin, roles & permissions (code),
master data, system settings, indexes/schema and the Excel templates (generated on demand).
Deletes: requisitions, candidates, applications, interviews, feedback, selections, offers, joinings,
costs, notifications, activity logs, file records, import batches and ID counters.

Usage (from the backend folder):
    python scripts/cleanup_recruitment_data.py                 # dry run: shows target + counts, deletes nothing
    python scripts/cleanup_recruitment_data.py --yes --database <DB_NAME>
The --database value must match DB_NAME in backend/.env, so the target is always stated explicitly.
"""
import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from core import db, client, log_activity  # noqa: E402
from routes_admin import environment, cleanup_counts, run_cleanup, RECRUITMENT_COLLECTIONS  # noqa: E402


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="actually delete (otherwise dry run)")
    ap.add_argument("--database", help="must equal DB_NAME — confirms the target database")
    a = ap.parse_args()
    env = environment()
    print(f"Target environment : {env['environment']}\nDatabase           : {env['database']}\nMongo host         : {env['mongo_host']}\n")
    counts = await cleanup_counts()
    for k, v in counts.items():
        print(f"  {RECRUITMENT_COLLECTIONS.get(k, k):<62} {v:>7}")
    if not a.yes:
        print("\nDry run only — nothing deleted. Re-run with --yes --database", env["database"])
        return
    if a.database != env["database"]:
        sys.exit(f"\nRefusing: --database '{a.database}' does not match the connected database '{env['database']}'.")
    if env["environment"].lower() in ("prod", "production"):
        if input(f"\nThis is PRODUCTION. Type the database name '{env['database']}' again to continue: ").strip() != env["database"]:
            sys.exit("Aborted.")
    deleted, remaining = await run_cleanup()
    await log_activity(None, "data_cleanup", "system", "cleanup", "Recruitment data cleared (CLI)",
                       ", ".join(f"{k}: {v}" for k, v in deleted.items()))
    print("\nDeleted per collection:")
    for k, v in deleted.items():
        print(f"  {RECRUITMENT_COLLECTIONS.get(k, k):<62} {v:>7}")
    print("\nVerification:", "all recruitment collections are empty" if not any(remaining.values()) else f"REMAINING {remaining}")
    print(f"Preserved: {await db.users.count_documents({})} users, {await db.masters.count_documents({})} master entries, "
          f"{await db.settings.count_documents({})} settings documents")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
