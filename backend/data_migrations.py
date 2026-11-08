"""One-time data migration: move every application currently in **Joined** back to **Screening**.

Status change only. Candidates, applications, requisition mappings, interviews and feedback, selections, offers and their
history, joining records and dates, CTC / consulting / recruiter fees (hire_cost) and all earlier history are left as they are.

Safety:
* preview() lists exactly what would change. Nothing is written.
* run() requires the count the operator saw in the preview. If the data changed since then, it refuses.
* The affected applications are copied in full to `migration_backups` before anything changes. rollback() restores them from there.
* The change runs inside a MongoDB transaction where the server supports it (Atlas does). Otherwise each update is
  guarded by `status == "Joined"`, so a re-run continues safely.
* Each run is recorded in `data_migrations`. Once it has completed, running it again changes nothing and writes no new audit entries.
* Afterwards, it checks that every target is in Screening and that no other application was touched.
"""
import hashlib
import os

from pymongo.errors import OperationFailure

from core import db, client, now_iso, new_id, recount_filled

MIGRATION_ID = "2026-11-08-joined-to-screening"
REASON = "Production candidate status reset"
CONFIRM_PHRASE = "MOVE JOINED TO SCREENING"


def environment():
    url = os.environ.get("MONGO_URL", "")
    host = url.split("://", 1)[-1].split("@")[-1].split("/")[0].split("?")[0] if url else "?"
    return {"database": os.environ.get("DB_NAME"), "mongo_host": host,
            "environment": os.environ.get("APP_ENV") or ("production" if "mongodb.net" in host else "local / test")}


async def _record():
    return await db.data_migrations.find_one({"id": MIGRATION_ID}, {"_id": 0})


async def preview():
    apps = await db.applications.find({"status": "Joined"}, {"_id": 0}).sort("code", 1).to_list(100000)
    cands = {c["id"]: c async for c in db.candidates.find({"id": {"$in": [a["candidate_id"] for a in apps]}}, {"_id": 0, "id": 1, "name": 1, "code": 1})}
    reqs = {r["id"]: r async for r in db.requisitions.find({"id": {"$in": list({a["requisition_id"] for a in apps})}},
                                                           {"_id": 0, "id": 1, "code": 1, "title": 1, "status": 1, "filled_positions": 1})}
    joins = {j["application_id"]: j async for j in db.joinings.find({"application_id": {"$in": [a["id"] for a in apps]}, "status": "Joined"},
                                                                  {"_id": 0, "application_id": 1, "actual_date": 1, "code": 1})}
    rows = [{"application_id": a["id"], "application_code": a.get("code"), "candidate_id": a["candidate_id"],
             "candidate_code": cands.get(a["candidate_id"], {}).get("code"), "candidate": cands.get(a["candidate_id"], {}).get("name"),
             "requisition_code": reqs.get(a["requisition_id"], {}).get("code"), "requisition_status": reqs.get(a["requisition_id"], {}).get("status"),
             "joining_code": joins.get(a["id"], {}).get("code"), "actual_join_date": joins.get(a["id"], {}).get("actual_date"),
             "has_cost": bool(a.get("hire_cost"))} for a in apps]
    rec = await _record()
    by_status = {}
    async for x in db.applications.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}]):
        by_status[x["_id"]] = x["n"]
    return {"migration_id": MIGRATION_ID, "reason": REASON, **environment(), "count": len(rows), "applications": rows,
            "total_applications": sum(by_status.values()), "by_status": by_status,
            "requisitions_affected": len(reqs), "closed_requisitions_affected": sorted({r["code"] for r in reqs.values() if r.get("status") in ("Closed", "Filled", "Cancelled")}),
            "already_applied": bool(rec and rec.get("status") == "completed"), "last_run": rec}


def _fingerprint(docs):
    h = hashlib.sha256()
    for d in sorted(docs, key=lambda x: x["id"]):
        h.update(f"{d['id']}|{d.get('status')}|{d.get('updated_at')}|{len(d.get('history') or [])}".encode())
    return h.hexdigest()


async def _others(target_ids):
    return [d async for d in db.applications.find({"id": {"$nin": target_ids}}, {"_id": 0, "id": 1, "status": 1, "updated_at": 1, "history": 1})]


async def run(actor_name="System", actor_id=None, expected_count=None):
    rec = await _record()
    if rec and rec.get("status") == "completed":
        return {"already_applied": True, "changed": 0, "last_run": rec,
                "message": f"Migration {MIGRATION_ID} already completed on {rec.get('completed_at')} — nothing changed."}
    targets = await db.applications.find({"status": "Joined"}, {"_id": 0}).to_list(100000)
    ids = [a["id"] for a in targets]
    if expected_count is None or int(expected_count) != len(ids):
        raise ValueError(f"The preview count ({expected_count}) does not match the applications now in Joined ({len(ids)}). Run the preview again.")
    total_before = await db.applications.count_documents({})
    others_before = _fingerprint(await _others(ids))
    run_id, ts = new_id(), now_iso()

    # 1. backup (full documents) — before anything changes
    req_ids = list({a["requisition_id"] for a in targets})
    filled_before = {r["id"]: r.get("filled_positions") async for r in db.requisitions.find({"id": {"$in": req_ids}}, {"_id": 0, "id": 1, "filled_positions": 1})}
    await db.migration_backups.insert_one({"id": run_id, "migration_id": MIGRATION_ID, "taken_at": ts, "taken_by": actor_name,
                                           "applications": targets, "filled_positions": filled_before})
    await db.data_migrations.update_one({"id": MIGRATION_ID}, {"$set": {"id": MIGRATION_ID, "status": "running", "started_at": ts, "run_id": run_id,
                                                                        "backup_id": run_id, "run_by": actor_name, "expected": len(ids)}}, upsert=True)

    async def apply(session=None):
        changed = 0
        cands = {c["id"]: c.get("name") async for c in db.candidates.find({"id": {"$in": [a["candidate_id"] for a in targets]}}, {"id": 1, "name": 1}, session=session)}
        for a in targets:
            entry = {"status": "Screening", "from": "Joined", "at": ts, "by": actor_name, "by_id": actor_id, "reason": REASON, "auto": False,
                     "note": f"Data migration {MIGRATION_ID}", "migration_id": MIGRATION_ID, "override": False, "override_reason": "", "records": []}
            res = await db.applications.update_one(
                {"id": a["id"], "status": "Joined", "migrations": {"$ne": MIGRATION_ID}},
                {"$set": {"status": "Screening", "closed": False, "stage_entered_at": ts, "updated_at": ts},
                 "$push": {"history": entry, "migrations": MIGRATION_ID}}, session=session)
            if res.modified_count:
                changed += 1
                await db.activity.insert_one({
                    "id": new_id(), "at": ts, "user_id": actor_id, "user_name": actor_name, "action": "status_migration",
                    "entity": "application", "entity_id": a["id"], "label": f"{cands.get(a['candidate_id'], '')} · {a.get('code', '')}",
                    "details": f"Joined → Screening · candidate {a['candidate_id']} · application {a['id']} · migration {MIGRATION_ID} · {REASON}",
                    "migration_id": MIGRATION_ID, "candidate_id": a["candidate_id"], "application_id": a["id"],
                    "previous_status": "Joined", "new_status": "Screening", "reason": REASON}, session=session)
        return changed

    transactional = True
    try:
        async with await client.start_session() as s:
            async with s.start_transaction():
                changed = await apply(s)
    except OperationFailure as e:  # standalone server (local dev): no transactions — guarded updates instead
        if e.code not in (20, 263) and "Transaction numbers" not in str(e) and "replica set" not in str(e):
            raise
        transactional = False
        changed = await apply(None)

    # 2. filled positions follow the applications that are still Joined (joining records are kept as history)
    for rid in req_ids:
        await recount_filled(rid)
    filled_after = {r["id"]: r.get("filled_positions") async for r in db.requisitions.find({"id": {"$in": req_ids}}, {"_id": 0, "id": 1, "filled_positions": 1})}

    # 3. verification
    now_screening = await db.applications.count_documents({"id": {"$in": ids}, "status": "Screening", "migrations": MIGRATION_ID})
    total_after = await db.applications.count_documents({})
    others_after = _fingerprint(await _others(ids))
    kept = {k: await db[k].count_documents({"application_id": {"$in": ids}}) for k in ("interviews", "selections", "offers", "joinings")}
    verify = {"targets": len(ids), "now_in_screening": now_screening, "all_moved": now_screening == len(ids),
              "application_count_unchanged": total_before == total_after, "other_applications_untouched": others_before == others_after,
              "related_records_kept": kept, "hire_costs_kept": await db.applications.count_documents({"id": {"$in": ids}, "hire_cost": {"$ne": None}}),
              "filled_positions_before": filled_before, "filled_positions_after": filled_after, "transactional": transactional}
    ok = verify["all_moved"] and verify["application_count_unchanged"] and verify["other_applications_untouched"]
    await db.data_migrations.update_one({"id": MIGRATION_ID}, {"$set": {"status": "completed" if ok else "needs_review", "completed_at": now_iso(),
                                                                        "changed": changed, "application_ids": ids, "verification": verify}})
    return {"already_applied": False, "changed": changed, "verification": verify, "ok": ok, "backup_id": run_id}


async def rollback(actor_name="System", actor_id=None):
    """Put the migrated applications back to Joined from the backup (only those still in Screening from this migration)."""
    rec = await _record()
    if not rec:
        raise ValueError("This migration has not been run")
    backup = await db.migration_backups.find_one({"id": rec["backup_id"]}, {"_id": 0})
    ts, restored = now_iso(), 0
    for a in backup["applications"]:
        res = await db.applications.update_one(
            {"id": a["id"], "status": "Screening", "migrations": MIGRATION_ID},
            {"$set": {"status": "Joined", "closed": True, "stage_entered_at": a.get("stage_entered_at"), "updated_at": ts},
             "$pull": {"migrations": MIGRATION_ID},
             "$push": {"history": {"status": "Joined", "from": "Screening", "at": ts, "by": actor_name, "by_id": actor_id,
                                   "reason": f"Rollback of {MIGRATION_ID}", "auto": False, "note": "Data migration rollback", "records": []}}})
        restored += res.modified_count
        if res.modified_count:
            await db.activity.insert_one({"id": new_id(), "at": ts, "user_id": actor_id, "user_name": actor_name, "action": "status_migration_rollback",
                                          "entity": "application", "entity_id": a["id"], "label": a.get("code", ""),
                                          "details": f"Screening → Joined · rollback of {MIGRATION_ID}", "migration_id": MIGRATION_ID})
    for rid in backup.get("filled_positions", {}):
        await recount_filled(rid)
    await db.data_migrations.update_one({"id": MIGRATION_ID}, {"$set": {"status": "rolled_back", "rolled_back_at": ts, "rolled_back_by": actor_name}})
    return {"restored": restored}
