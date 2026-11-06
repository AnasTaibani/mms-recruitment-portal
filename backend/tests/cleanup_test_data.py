# Cleanup: restore DB to "empty" state (keeps super admin, settings, baseline seeded masters)
import json
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
base = json.load(open("/tmp/baseline.json"))
for c in ["requisitions", "candidates", "applications", "interviews", "feedback", "offers", "joinings", "costs",
          "selections", "notifications", "files", "counters", "login_attempts"]:
    db[c].delete_many({})
db.activity.delete_many({"id": {"$nin": base["a"]}})
db.import_batches.delete_many({"id": {"$nin": base["ib"]}})
db.masters.delete_many({"id": {"$nin": base["m"]}})
db.users.delete_many({"role": {"$ne": "super_admin"}})
db.users.delete_many({"email": {"$ne": "anastaibani53@gmail.com"}})
print({c: db[c].count_documents({}) for c in db.list_collection_names()})
