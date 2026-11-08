import io
import re
from datetime import datetime, date, time
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from pydantic import BaseModel

from workflow import reached_index
from core import (db, require, now_iso, today, new_id, next_code, log_activity, parse_date, parse_num, get_settings,
                  recount_filled, ALL_STATUSES, INACTIVE, TERMINAL, REQ_STATUSES, INTERVIEW_STATUSES, INTERVIEW_MODES,
                  PAYMENT_STATUSES)
from routes_recruit import norm_phone, cand_fields
from templates_xlsx import TEMPLATES, SAMPLE_TAG, PARTNER_TYPES, OUTCOME_LIST, build_template

router = APIRouter(prefix="/api/import")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

LEGACY_FIELDS = {
    "candidates": {"role": "Role / Requisition (legacy)", "status": "Status (legacy)",
                   **{f"r{i}_{k}": f"Round {i} {k.title()} (legacy)" for i in (1, 2, 3) for k in ("date", "interviewer", "outcome")}},
    "requisitions": {"salary_range": "Salary Range (e.g. 7-18 LPA)", "pipeline_note": "Pipeline Note"},
}
FIELDS = {k: {f: h for h, f, *_ in t["columns"]} | LEGACY_FIELDS.get(k, {}) for k, t in TEMPLATES.items()} | {"interviewers": {}}
KIND = {k: {f: kind for _, f, _, kind, *_ in t["columns"]} for k, t in TEMPLATES.items()}
LKEY = {k: {f: lk for _, f, _, _, lk, _ in t["columns"]} for k, t in TEMPLATES.items()}
REQUIRED = {k: [f for _, f, req, *_ in t["columns"] if req] for k, t in TEMPLATES.items()}
MASTER_KEYS = {"job_title", "department", "hiring_manager", "recruiter", "location", "employment_type", "priority", "source",
               "partner", "round_type", "interviewer", "cost_category"}
FIXED = {"req_status": REQ_STATUSES, "app_status": ALL_STATUSES, "iv_status": INTERVIEW_STATUSES, "mode": INTERVIEW_MODES,
         "payment_status": PAYMENT_STATUSES, "outcome": OUTCOME_LIST, "partner_type": PARTNER_TYPES}
ALIASES = {
    "name": ["candidate name", "name", "full name"], "email": ["email id", "email", "email address"],
    "phone": ["contact number", "contact no", "mobile", "mobile number", "phone"], "current_company": ["current company", "company"],
    "current_location": ["current location"], "source": ["source", "candidate source"], "role": ["role", "position", "applied role"],
    "notice_period": ["notice period", "np"], "current_designation": ["current designation", "designation"],
    "qualification": ["educational degree", "qualification", "education"], "current_ctc": ["current ctc", "ctc"],
    "expected_ctc": ["expected ctc", "exp ctc"], "recruiter": ["recruiter", "assigned recruiter"],
    "r1_date": ["first interview date"], "r1_interviewer": ["first interviewer", "interviewer i"], "r1_outcome": ["first interview outcome"],
    "r2_date": ["second interview date"], "r2_interviewer": ["second interviewer", "round ii interviewer"], "r2_outcome": ["second interview outcome"],
    "r3_date": ["third interview date"], "r3_interviewer": ["third interviewer", "hr interviewer"], "r3_outcome": ["third interview outcome"],
    "status": ["status"], "remarks": ["remarks"], "partner": ["consultant", "consultancy", "recruitment partner", "partner"],
    "total_exp": ["experience", "total experience"], "relevant_exp": ["relevant experience"],
    "title": ["role", "job title", "position"], "positions": ["open positions", "positions", "no of positions"],
    "experience": ["desired experience", "required experience", "experience"], "salary_range": ["salary range", "ctc range"],
    "hiring_manager": ["hiring manager"], "department": ["allocation", "department", "business function"],
    "location": ["preferred location", "location"], "crf_date": ["request raised on", "crf raised date", "crf date"],
    "initiation_date": ["recruitment initiation date", "initiation date"], "pipeline_note": ["pipeline"], "priority": ["priority"],
}
LEGACY_STATUS = {"to be interviewed": "Shortlisted", "interview": "Interview Scheduled", "to be offered": "Selected",
                 "offer extended": "Offer Released", "accepted offer": "Offer Accepted"} | {s.lower(): s for s in ALL_STATUSES}
OUTCOMES = {"selected": "Selected", "rejected": "Rejected", "on hold": "On Hold", "pending": "Pending", "no show": "No Show"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def cell(v):
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d") if (v.hour, v.minute) == (0, 0) or v.year > 1900 else v.strftime("%H:%M")
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, time):
        return v.strftime("%H:%M")
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str):
        v = v.replace("\xa0", " ").strip()
        return None if v in ("", "-") else v
    return v


def clean(s):
    return re.sub(r"\s+", " ", str(s or "").replace("\xa0", " ")).strip()


def head_key(h):
    return clean(h).rstrip("*†").strip().lower()


def detect_header(rows):
    for i, r in enumerate(rows[:10]):
        if sum(1 for c in r if isinstance(c, str) and c.strip()) >= 3:
            return i
    return 0


def detect_template(name, headers):
    hs = {head_key(h) for h in headers if h}
    for k, t in TEMPLATES.items():
        th = {h.lower() for h, *_ in t["columns"]}
        if name.strip().lower() == t["sheet"].lower() or len(hs & th) >= 0.7 * len(th):
            return k
    return None


def suggest(headers, itype, template):
    out, used = {}, set()
    low = {head_key(h): h for h in headers if h}
    if template:
        for h, f, *_ in TEMPLATES[itype]["columns"]:
            if h.lower() in low:
                out[f] = low[h.lower()]
        return out
    for field in FIELDS.get(itype, {}):
        for alias in ALIASES.get(field, []):
            if alias in low and low[alias] not in used:
                out[field] = low[alias]
                used.add(low[alias])
                break
    return out


def guess_type(name, headers):
    hs = {head_key(h) for h in headers if h}
    if "open positions" in hs and "hiring manager" in hs:
        return "requisitions"
    if "candidate name" in hs or "email id" in hs or "name" in hs and ("email" in hs or "contact no" in hs):
        return "candidates"
    if "interviewer" in name.lower():
        return "interviewers"
    return None


# ---------- templates ----------
@router.get("/templates")
async def list_templates(user=Depends(require("import.run"))):
    return [{"key": k, "title": t["title"], "sheet": t["sheet"],
             "columns": [{"header": h, "required": r} for h, _, r, *_ in t["columns"]]} for k, t in TEMPLATES.items()]


@router.get("/templates/{key}")
async def download_template(key: str, user=Depends(require("import.run"))):
    if key not in TEMPLATES:
        raise HTTPException(404, "Unknown template")
    data, fname = await build_template(key)
    return StreamingResponse(io.BytesIO(data), media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ---------- upload ----------
@router.post("/upload")
async def upload(file: UploadFile = File(...), user=Depends(require("import.run"))):
    if not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "Please upload an .xlsx workbook")
    data = await file.read()
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        raise HTTPException(400, "The file could not be read as an Excel workbook")
    sheets = []
    for ws in wb.worksheets:
        if ws.title in ("Instructions", "Lists"):
            continue
        rows = [[cell(c) for c in r] for r in ws.iter_rows(values_only=True)]
        rows = [r for r in rows if any(c is not None for c in r)]
        if not rows:
            continue
        width = max(len(r) for r in rows)
        rows = [r + [None] * (width - len(r)) for r in rows]
        h = detect_header(rows)
        headers = [clean(c) if c is not None else f"Column {i + 1}" for i, c in enumerate(rows[h])]
        tkey = detect_template(ws.title, headers)
        itype = tkey or guess_type(ws.title, headers)
        sheets.append({"name": ws.title, "header_row": h, "headers": headers, "rows": rows[h + 1:],
                       "row_count": len(rows) - h - 1, "suggested_type": itype, "template": tkey,
                       "suggested_mapping": suggest(headers, itype, bool(tkey)) if itype and itype != "interviewers" else {}})
    if not sheets:
        raise HTTPException(400, "The workbook has no data sheets")
    batch = {"id": new_id(), "filename": file.filename, "uploaded_by": user["name"], "created_at": now_iso(), "sheets": sheets}
    await db.import_batches.insert_one(batch)
    return {"id": batch["id"], "filename": file.filename, "fields": FIELDS, "required": REQUIRED,
            "sheets": [{k: v for k, v in s.items() if k != "rows"} | {"preview": s["rows"][:8]} for s in sheets]}


class ValidateIn(BaseModel):
    batch_id: str
    sheet: str
    type: str
    mapping: Dict[str, str] = {}
    columns: List[str] = []
    skip_duplicates: bool = True
    create_missing_roles: bool = False
    create_missing_masters: bool = False
    update_existing: bool = False


async def load(body):
    b = await db.import_batches.find_one({"id": body.batch_id}, {"_id": 0})
    if not b:
        raise HTTPException(404, "Import batch not found — upload again")
    s = next((x for x in b["sheets"] if x["name"] == body.sheet), None)
    if not s or body.type not in FIELDS:
        raise HTTPException(400, "Choose a sheet and import type")
    return b, s


def salary(v):
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", str(v or ""))]
    if not nums:
        return None, None
    if len(nums) >= 2:
        return nums[0], nums[1]
    return (None, nums[0]) if re.search(r"upto|up to|max", str(v), re.I) else (nums[0], nums[0])


def clean_person(n):
    n = clean(n)
    n = re.sub(r"\s*[-–]\s*(yes.*)?$", "", n, flags=re.I).strip()
    return n or None


class Masters:
    def __init__(self):
        self.by = {}

    async def load(self):
        async for m in db.masters.find({}, {"_id": 0, "id": 1, "type": 1, "name": 1, "email": 1}):
            d = self.by.setdefault(m["type"], {})
            d[m["name"].strip().lower()] = m["id"]
            if m.get("email"):
                d[m["email"].strip().lower()] = m["id"]
        return self

    def get(self, mtype, value):
        return self.by.get(mtype, {}).get(clean(value).lower()) if value else None


class Lookups:
    async def load(self):
        self.reqs_by_code, self.reqs_by_title = {}, {}
        async for r in db.requisitions.find({}, {"_id": 0}):
            self.reqs_by_code[r["code"].upper()] = r
            if r["status"] != "Cancelled":
                self.reqs_by_title.setdefault(clean(r["title"]).lower(), r)
        self.cand_code, self.cand_email, self.cand_phone = {}, {}, {}
        async for c in db.candidates.find({}, {"_id": 0, "id": 1, "code": 1, "email": 1, "phone_norm": 1}):
            self.cand_code[c["code"].upper()] = c["id"]
            if c.get("email"):
                self.cand_email[c["email"]] = c["id"]
            if c.get("phone_norm"):
                self.cand_phone[c["phone_norm"]] = c["id"]
        self.apps = {(a["candidate_id"], a["requisition_id"]): a["id"] async for a in db.applications.find({}, {"candidate_id": 1, "requisition_id": 1, "id": 1})}
        return self

    def cand(self, ref):
        ref = clean(ref)
        return self.cand_code.get(ref.upper()) or self.cand_email.get(ref.lower()) if ref else None


class Row:
    def __init__(self, row_no, raw, mapping):
        self.row, self.raw, self.mapping = row_no, raw, mapping
        self.errors, self.warnings, self.cols, self.data = [], [], set(), {}
        self.status = "valid"

    def err(self, field, msg, label=None):
        col = self.mapping.get(field) or label or field
        self.errors.append(f"{col.rstrip('*†')}: {msg}")
        self.cols.add(col)

    def warn(self, field, msg):
        col = self.mapping.get(field) or field
        self.warnings.append(f"{col.rstrip('*†')}: {msg}")

    def out(self):
        status = "error" if self.errors else self.status
        return {"row": self.row, "status": status, "messages": self.errors + self.warnings, "error_columns": sorted(self.cols),
                "data": self.data, "raw": self.raw}


def convert(r, itype, field, v, strict):
    kind = KIND.get(itype, {}).get(field, "date" if field.endswith("_date") else "text")
    if v is None:
        return None
    if kind == "date":
        d = parse_date(v)
        if not d:
            r.err(field, f"'{v}' is not a valid date — use DD-MM-YYYY")
        return d
    if kind in ("int", "num"):
        if isinstance(v, (int, float)):
            n = float(v)
        elif strict and not re.fullmatch(r"\s*-?\d+(\.\d+)?\s*", str(v).replace(",", "")):
            r.err(field, f"'{v}' is not a number")
            return None
        else:
            n = parse_num(v)
        if n is not None and n < 0:
            r.err(field, "cannot be negative")
        if kind == "int" and n is not None and not float(n).is_integer():
            r.err(field, "must be a whole number")
        return int(n) if kind == "int" and n is not None else n
    if kind == "time":
        s = clean(v)
        m = re.fullmatch(r"(\d{1,2})[:.](\d{2})(?::\d{2})?", s)
        if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
            r.err(field, f"'{v}' is not a valid time — use HH:MM")
            return None
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    if kind == "email":
        e = clean(v).lower().strip("|;, ")
        if not EMAIL_RE.match(e):
            (r.err if strict else r.warn)(field, f"'{v}' is not a valid email" + ("" if strict else " — left blank"))
            return None
        return e
    return clean(v)


def resolve_master(r, field, mtype, value, ms, create):
    if not value:
        return None
    if ms.get(mtype, value):
        return value
    if create:
        r.warn(field, f"'{value}' will be added to master data")
        return value
    r.err(field, f"'{value}' is not in master data")
    return None


def fixed(r, field, lkey, value, default=None):
    if not value:
        return default
    match = next((x for x in FIXED[lkey] if x.lower() == clean(value).lower()), None)
    if not match:
        r.err(field, f"'{value}' is not an allowed value")
    return match


async def validate_rows(body, s):
    if body.type == "interviewers":
        return await validate_interviewers(body, s)
    m = {f: h for f, h in body.mapping.items() if h}
    template = bool(s.get("template"))
    missing = [FIELDS[body.type][f] for f in REQUIRED.get(body.type, []) if f not in m and not (body.type == "costs")]
    if body.type == "requisitions" and not template:
        missing = [FIELDS["requisitions"][f] for f in ("title", "positions") if f not in m]
    if missing:
        raise HTTPException(400, f"Map the mandatory column(s): {', '.join(missing)}")
    ms, lk = await Masters().load(), await Lookups().load()
    scale = (await get_settings()).get("rating_scale", 5)
    create = body.create_missing_masters
    seen, out = {}, []
    idx = {h: i for i, h in enumerate(s["headers"])}
    for rn, raw in enumerate(s["rows"]):
        g = {f: raw[idx[h]] for f, h in m.items() if h in idx}
        if all(v is None for v in g.values()):
            continue
        r = Row(rn + s["header_row"] + 2, raw, m)
        if any(isinstance(c, str) and SAMPLE_TAG in c for c in raw):
            r.status = "sample"
            r.warnings.append(f"Sample row — ignored (clear the {SAMPLE_TAG} tag in Remarks if this is real data)")
            out.append(r.out())
            continue
        for f in REQUIRED.get(body.type, []):
            if body.type != "costs" and g.get(f) is None:
                r.err(f, "is mandatory", FIELDS[body.type][f])
        d = {f: convert(r, body.type, f, v, template) for f, v in g.items()}
        lkeys = LKEY.get(body.type, {})
        for f, v in list(d.items()):
            lkey = lkeys.get(f)
            if lkey in MASTER_KEYS and f not in ("interviewers", "title", "partner"):
                d[f] = resolve_master(r, f, lkey, clean_person(v) if lkey in ("recruiter", "hiring_manager") else v, ms, create)
        await VALIDATORS[body.type](r, d, body, lk, ms, seen, template, scale)
        r.data = r.data or d
        out.append(r.out())
    return out


async def v_requisitions(r, d, body, lk, ms, seen, template, scale):
    if d.get("title") and template:
        resolve_master(r, "title", "job_title", d["title"], ms, body.create_missing_masters or not ms.by.get("job_title"))
    pos = d.get("positions")
    if pos is not None and pos < 1:
        r.err("positions", "must be at least 1")
    if d.get("salary_range"):
        mn, mx = salary(d.pop("salary_range"))
        d.setdefault("min_ctc", mn)
        d["max_ctc"] = d.get("max_ctc") or mx
    if d.get("min_ctc") is not None and d.get("max_ctc") is not None and d["min_ctc"] > d["max_ctc"]:
        r.err("max_ctc", "Maximum CTC is lower than Minimum CTC")
    d["status"] = fixed(r, "status", "req_status", d.get("status"), "Open")
    if d.get("pipeline_note"):
        d["remarks"] = " · ".join(x for x in (d.get("remarks"), f"Pipeline: {d.pop('pipeline_note')}") if x)
    if not d.get("crf_date"):
        r.warn("crf_date", "missing — Age per Hire will be unavailable for this requisition")
    if d.get("skills"):
        d["skills"] = [x.strip() for x in d["skills"].split(",") if x.strip()]
    code = (d.get("code") or "").upper()
    if code:
        d["code"] = code
        if code in seen:
            r.err("code", f"Requisition ID repeated (row {seen[code]})")
        seen.setdefault(code, r.row)
        if code in lk.reqs_by_code:
            d["existing_id"] = lk.reqs_by_code[code]["id"]
            r.status = "update" if body.update_existing else "duplicate"
            r.warnings.append(f"Requisition {code} already exists" + (" — will be updated" if body.update_existing else ""))
    elif d.get("title"):
        t = d["title"].lower()
        if "code" in body.mapping:
            if t in lk.reqs_by_title:
                r.warn("title", f"a requisition titled '{d['title']}' already exists ({lk.reqs_by_title[t]['code']}) — a new one will be created")
        elif t in lk.reqs_by_title or ("t:" + t) in seen:
            r.status = "duplicate"
            r.warnings.append("A requisition with this title already exists")
        seen.setdefault("t:" + t, r.row)


async def v_candidates(r, d, body, lk, ms, seen, template, scale):
    if d.get("partner"):
        d["partner"] = resolve_master(r, "partner", "partner", d["partner"], ms, body.create_missing_masters)
    phone = norm_phone(d.get("phone"))
    if d.get("phone") and len(phone) < 10:
        (r.err if template else r.warn)("phone", f"'{d['phone']}' is not a valid 10-digit mobile number")
    email = d.get("email")
    if not email and not phone:
        (r.err if template else r.warn)("email", "Email or Mobile Number is required")
    code = (d.get("code") or "").upper()
    d["code"] = code or None
    existing = (lk.cand_code.get(code) if code else None) or (lk.cand_email.get(email) if email else None) or (lk.cand_phone.get(phone) if phone else None)
    keys = [k for k in (f"c:{code}" if code else None, f"e:{email}" if email else None, f"p:{phone}" if phone else None) if k]
    dup_row = next((seen[k] for k in keys if k in seen), None)
    for k in keys:
        seen.setdefault(k, r.row)
    if existing:
        d["existing_id"] = existing
        r.status = "update" if body.update_existing else "duplicate"
        r.warnings.append("Matches an existing candidate (email / mobile / ID)" + (" — will be updated" if body.update_existing else ""))
    elif dup_row:
        r.status = "duplicate"
        r.warnings.append(f"Same person as row {dup_row} in this file")
    if d.get("source") is None and d.get("partner") and not template:
        d["source"] = "Consultant"
    legacy = d.get("status")
    if legacy is not None or "role" in body.mapping:
        st = LEGACY_STATUS.get(legacy.lower(), "New") if legacy else "New"
        if legacy and legacy.lower() not in LEGACY_STATUS:
            r.warn("status", f"unknown status '{legacy}' → New")
        d["status"] = st
        role = d.get("role")
        if role and role.lower() not in lk.reqs_by_title:
            r.warn("role", f"Requisition '{role}' will be created" if body.create_missing_roles else f"no requisition titled '{role}' — imported without an application")
        if st == "Joined":
            r.warn("status", "Joined without an actual joining date — excluded from Age per Hire")
        rounds = []
        for i in (1, 2, 3):
            dt, iv, oc = d.pop(f"r{i}_date", None), clean_person(d.pop(f"r{i}_interviewer", None)), d.pop(f"r{i}_outcome", None)
            if dt or iv:
                rounds.append({"n": i, "date": dt, "interviewer": iv, "outcome": OUTCOMES.get((oc or "").lower(), "Pending")})
        d["rounds"] = rounds


async def v_applications(r, d, body, lk, ms, seen, template, scale):
    cid = lk.cand(d.get("candidate_ref"))
    req = lk.reqs_by_code.get((d.get("requisition_code") or "").upper())
    if d.get("candidate_ref") and not cid:
        r.err("candidate_ref", f"no candidate with ID or email '{d['candidate_ref']}'")
    if d.get("requisition_code") and not req:
        r.err("requisition_code", f"Requisition ID '{d['requisition_code']}' not found")
    d["status"] = fixed(r, "status", "app_status", d.get("status"), "New")
    if d["status"] in TERMINAL and not d.get("remarks"):
        r.err("remarks", f"a reason is required for status '{d['status']}'")
    if d["status"] == "Joined" and not d.get("actual_join_date"):
        r.err("actual_join_date", "required when status is Joined")
    if d["status"] == "Joined" and req and req.get("crf_date") and d.get("actual_join_date") and d["actual_join_date"] < req["crf_date"]:
        r.warn("actual_join_date", "precedes the requisition's CRF Raised Date — Age per Hire will be flagged")
    if cid and req:
        d["candidate_id"], d["requisition_id"] = cid, req["id"]
        key = f"{cid}:{req['id']}"
        if key in seen:
            r.err("requisition_code", f"same candidate and requisition already in row {seen[key]}")
        seen.setdefault(key, r.row)
        if (cid, req["id"]) in lk.apps:
            d["existing_id"] = lk.apps[(cid, req["id"])]
            r.status = "update" if body.update_existing else "duplicate"
            r.warnings.append("Candidate is already mapped to this requisition" + (" — status will be updated" if body.update_existing else ""))


async def v_interviews(r, d, body, lk, ms, seen, template, scale):
    cid = lk.cand(d.get("candidate_ref"))
    req = lk.reqs_by_code.get((d.get("requisition_code") or "").upper())
    if d.get("candidate_ref") and not cid:
        r.err("candidate_ref", f"no candidate with ID or email '{d['candidate_ref']}'")
    if d.get("requisition_code") and not req:
        r.err("requisition_code", f"Requisition ID '{d['requisition_code']}' not found")
    if cid and req:
        aid = lk.apps.get((cid, req["id"]))
        if not aid:
            r.err("requisition_code", "candidate is not mapped to this requisition — import the Candidate-Requisition Mapping first")
        d |= {"candidate_id": cid, "requisition_id": req["id"], "application_id": aid}
    ids = []
    for name in re.split(r"[,;/]", d.get("interviewers") or ""):
        name = clean_person(name)
        if not name:
            continue
        if ms.get("interviewer", name):
            ids.append(name)
        elif body.create_missing_masters:
            r.warn("interviewers", f"'{name}' will be added to master data")
            ids.append(name)
        else:
            r.err("interviewers", f"'{name}' is not in the interviewer master")
    d["interviewer_names"] = ids
    d["status"] = fixed(r, "status", "iv_status", d.get("status"), "Scheduled")
    d["outcome"] = fixed(r, "outcome", "outcome", d.get("outcome"), "Pending")
    d["mode"] = fixed(r, "mode", "mode", d.get("mode"))
    if d.get("rating") is not None and not 1 <= d["rating"] <= scale:
        r.err("rating", f"must be between 1 and {scale}")
    if d.get("start_time") and d.get("end_time") and d["end_time"] <= d["start_time"]:
        r.err("end_time", "must be after Start Time")
    if d.get("application_id") and d.get("round_number"):
        key = f"{d['application_id']}:{d['round_number']}"
        if key in seen:
            r.err("round_number", f"same round already in row {seen[key]}")
        seen.setdefault(key, r.row)
        ex = await db.interviews.find_one({"application_id": d["application_id"], "round_number": d["round_number"], "status": {"$ne": "Cancelled"}}, {"id": 1})
        if ex:
            d["existing_id"] = ex["id"]
            r.status = "update" if body.update_existing else "duplicate"
            r.warnings.append(f"Round {d['round_number']} already exists for this application" + (" — will be updated" if body.update_existing else ""))


async def v_costs(r, d, body, lk, ms, seen, template, scale):
    if d.get("partner") and not ms.get("partner", d["partner"]):
        r.warn("partner", f"new partner '{d['partner']}' will be added to master data")
    d["partner_type"] = fixed(r, "partner_type", "partner_type", d.get("partner_type"))
    cost_fields = ("category", "requisition_code", "candidate_ref", "invoice_no", "invoice_date", "amount", "payment_status", "payment_date")
    d["has_cost"] = any(d.get(f) is not None for f in cost_fields)
    if not d["has_cost"]:
        if not d.get("partner"):
            r.err("partner", "Recruitment Partner Name or cost details are required")
        return
    for f in ("category", "invoice_date", "amount"):
        if d.get(f) is None and not any(f"{FIELDS['costs'][f]}" in e for e in r.errors):
            r.err(f, "is mandatory for cost rows", FIELDS["costs"][f])
    if d.get("category"):
        d["category"] = resolve_master(r, "category", "cost_category", d["category"], ms, body.create_missing_masters)
    if d.get("amount") is not None and d["amount"] <= 0:
        r.err("amount", "must be greater than 0")
    d["payment_status"] = fixed(r, "payment_status", "payment_status", d.get("payment_status"), "Pending")
    if d.get("requisition_code"):
        req = lk.reqs_by_code.get(d["requisition_code"].upper())
        if not req:
            r.err("requisition_code", f"Requisition ID '{d['requisition_code']}' not found")
        d["requisition_id"] = req and req["id"]
    if d.get("candidate_ref"):
        d["candidate_id"] = lk.cand(d["candidate_ref"])
        if not d["candidate_id"]:
            r.err("candidate_ref", f"no candidate with ID or email '{d['candidate_ref']}'")
    if d.get("invoice_no"):
        key = f"{(d.get('partner') or '').lower()}:{d['invoice_no'].lower()}"
        if key in seen:
            r.err("invoice_no", f"same invoice already in row {seen[key]}")
        seen.setdefault(key, r.row)
        pid = ms.get("partner", d.get("partner"))
        ex = await db.costs.find_one({"invoice_no": {"$regex": f"^{re.escape(d['invoice_no'])}$", "$options": "i"}, "partner_id": pid}, {"id": 1})
        if ex:
            d["existing_id"] = ex["id"]
            r.status = "update" if body.update_existing else "duplicate"
            r.warnings.append("Invoice already recorded for this partner" + (" — will be updated" if body.update_existing else ""))


VALIDATORS = {"requisitions": v_requisitions, "candidates": v_candidates, "applications": v_applications,
              "interviews": v_interviews, "costs": v_costs}


async def validate_interviewers(body, s):
    cols = body.columns or [h for h in s["headers"] if not h.startswith("Column")]
    idx = {h: i for i, h in enumerate(s["headers"])}
    existing = {m["name"].lower() async for m in db.masters.find({"type": "interviewer"}, {"name": 1})}
    people = {}
    for rn, r in enumerate(s["rows"]):
        for h in cols:
            n = clean_person(r[idx[h]]) if idx.get(h) is not None else None
            if not n or n.lower() in ("name", "round 2"):
                continue
            p = people.setdefault(n.lower(), {"row": rn + s["header_row"] + 2, "name": n, "areas": []})
            if h not in p["areas"]:
                p["areas"].append(h)
    out = []
    for p in people.values():
        dup = p["name"].lower() in existing
        out.append({"row": p["row"], "status": "duplicate" if dup else "valid", "messages": ["Interviewer already exists"] if dup else [],
                    "error_columns": [], "data": {"name": p["name"], "skill_area": ", ".join(p["areas"])}, "raw": [p["name"], ", ".join(p["areas"])]})
    return out


def summarize(rows):
    s = {k: sum(1 for r in rows if r["status"] == k) for k in ("valid", "update", "duplicate", "error", "sample")}
    s["total"] = len(rows)
    s["warnings"] = sum(1 for r in rows if r["messages"] and r["status"] in ("valid", "update"))
    return s


async def store_report(b, s, body, rows, stage):
    headers = ["Excel Row", "Result", "Issues"] + (s["headers"] if body.type != "interviewers" else ["Name", "Skill Areas"])
    bad = [r for r in rows if r["status"] in ("error", "duplicate")]
    await db.import_batches.update_one({"id": b["id"]}, {"$set": {"rejected": {
        "headers": headers, "stage": stage, "sheet": s["name"],
        "rows": [{"values": [r["row"], r["status"], "; ".join(r["messages"])] + list(r["raw"]), "error_columns": r.get("error_columns", [])} for r in bad]}}})
    return len(bad)


@router.post("/validate")
async def validate(body: ValidateIn, user=Depends(require("import.run"))):
    b, s = await load(body)
    rows = await validate_rows(body, s)
    report = await store_report(b, s, body, rows, "validation")
    return {"summary": summarize(rows), "report_rows": report,
            "rows": [{k: v for k, v in r.items() if k != "raw"} | {"data": {k: v for k, v in r["data"].items() if not isinstance(v, (list, dict)) or k == "skills"}} for r in rows]}


# ---------- commit ----------
class Ctx:
    def __init__(self, user, source, create):
        self.user, self.source, self.create, self.cache = user, source, create, {}
        self.inserted, self.updated, self.logs, self.reqs = [], [], [], set()

    async def insert(self, coll, doc):
        await db[coll].insert_one(doc)
        self.inserted.append((coll, doc["id"]))
        return doc

    async def update(self, coll, id_, changes):
        before = await db[coll].find_one({"id": id_}, {"_id": 0})
        self.updated.append((coll, id_, before))
        await db[coll].update_one({"id": id_}, {"$set": changes})
        return before

    async def rollback(self):
        for coll, id_ in reversed(self.inserted):
            await db[coll].delete_one({"id": id_})
        for coll, id_, before in reversed(self.updated):
            if before:
                await db[coll].replace_one({"id": id_}, before)
        for rid in self.reqs:  # filled_positions is derived — recompute after undoing joinings
            await recount_filled(rid)
        self.logs = []

    async def flush_logs(self):
        """Activity entries are written only after the whole import succeeds, so a rolled-back import leaves no trace."""
        for action, entity, id_, label in self.logs:
            await log_activity(self.user, action, entity, id_, label, self.source)
        self.logs = []

    async def master(self, mtype, name, extra=None):
        if not name:
            return None
        key = (mtype, name.lower())
        if key in self.cache:
            return self.cache[key]
        m = await db.masters.find_one({"type": mtype, "$or": [{"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
                                                               {"email": name.lower()}]})
        if not m:
            m = await self.insert("masters", {"id": new_id(), "type": mtype, "name": name, "active": True, "user_id": None,
                                              "created_at": now_iso(), "notes": "Created by Excel import"} | (extra or {}))
        self.cache[key] = m["id"]
        return m["id"]

    async def log(self, action, entity, id_, label):
        self.logs.append((action, entity, id_, label))


async def unique_code(coll, prefix, width=4, wanted=None):
    if wanted and not await db[coll].find_one({"code": wanted}):
        return wanted
    while True:
        c = await next_code(prefix, width)
        if not await db[coll].find_one({"code": c}):
            return c


def present(d, keys):
    return {k: d[k] for k in keys if d.get(k) not in (None, "", [])}


REQ_KEYS = ("title", "positions", "experience", "min_ctc", "max_ctc", "skills", "qualifications", "crf_date", "initiation_date", "status", "remarks")


async def req_refs(ctx, d):
    return {k: v for k, v in {
        "department_id": await ctx.master("department", d.get("department")),
        "hiring_manager_id": await ctx.master("hiring_manager", d.get("hiring_manager")),
        "recruiter_id": await ctx.master("recruiter", d.get("recruiter")),
        "location_id": await ctx.master("location", d.get("location")),
        "employment_type_id": await ctx.master("employment_type", d.get("employment_type")),
        "priority_id": await ctx.master("priority", d.get("priority")),
        "job_title_id": await ctx.master("job_title", d.get("title"))}.items() if v}


async def w_requisitions(ctx, d, body):
    ts = now_iso()
    refs = await req_refs(ctx, d)
    if d.get("existing_id"):
        await ctx.update("requisitions", d["existing_id"], present(d, REQ_KEYS) | refs | {"updated_at": ts})
        await ctx.log("import_update", "requisition", d["existing_id"], d["code"])
        return "updated"
    doc = {"id": new_id(), "code": await unique_code("requisitions", "REQ", 4, d.get("code")), "title": d["title"],
           "positions": d.get("positions") or 1, "experience": d.get("experience"), "min_ctc": d.get("min_ctc"), "max_ctc": d.get("max_ctc"),
           "skills": d.get("skills") or [], "qualifications": d.get("qualifications"), "crf_date": d.get("crf_date"),
           "initiation_date": d.get("initiation_date"), "status": d.get("status") or "Open", "remarks": d.get("remarks"),
           "filled_positions": 0, "created_by": ctx.user["id"], "created_by_name": ctx.user["name"], "created_at": ts,
           "updated_at": ts, "import_source": ctx.source} | refs
    await ctx.insert("requisitions", doc)
    await ctx.log("import", "requisition", doc["id"], f"{doc['code']} {doc['title']}")
    return "imported"


CAND_KEYS = ("name", "email", "phone", "current_company", "current_designation", "current_location", "total_exp", "relevant_exp",
             "qualification", "current_ctc", "expected_ctc", "notice_period", "last_working_day", "available_from", "resume_ref", "remarks")


async def create_app(ctx, cand_id, req, status, remarks, recruiter_id=None, app_date=None, join_date=None):
    ts = now_iso()
    app = await ctx.insert("applications", {
        "id": new_id(), "code": await unique_code("applications", "APP", 5), "candidate_id": cand_id, "requisition_id": req["id"],
        "recruiter_id": recruiter_id or req.get("recruiter_id"), "status": status, "stage_entered_at": ts, "closed": status in INACTIVE,
        "created_at": f"{app_date}T00:00:00+00:00" if app_date else ts, "updated_at": ts, "created_by": ctx.user["id"], "import_source": ctx.source,
        "legacy_stage_index": reached_index({"status": status}),  # imported history: earlier stages are accepted as historical, never fabricated
        "history": [{"status": status, "from": None, "at": ts, "by": ctx.user["name"], "reason": remarks or "", "auto": False, "note": "Imported from Excel"}]})
    if status == "Joined":
        await upsert_joining(ctx, app, join_date, remarks)
    await ctx.log("import", "application", app["id"], f"{app['code']} → {status}")
    return app


async def upsert_joining(ctx, app, join_date, remarks):
    ts = now_iso()
    cand = await db.candidates.find_one({"id": app["candidate_id"]}, {"_id": 0, "partner_id": 1})
    j = await db.joinings.find_one({"application_id": app["id"]}, {"_id": 0})
    if j:
        await ctx.update("joinings", j["id"], {"status": "Joined", "actual_date": join_date, "updated_at": ts})
    else:
        await ctx.insert("joinings", {"id": new_id(), "code": await unique_code("joinings", "JN"), "application_id": app["id"],
                                      "candidate_id": app["candidate_id"], "requisition_id": app["requisition_id"],
                                      "recruiter_id": app.get("recruiter_id"), "partner_id": (cand or {}).get("partner_id"),
                                      "status": "Joined", "actual_date": join_date, "tentative_date": None, "confirmed_date": None,
                                      "checklist": [], "remarks": remarks or "Imported", "created_at": ts, "updated_at": ts,
                                      "history": [{"at": ts, "by": ctx.user["name"], "action": "Joined", "details": "Imported"}]})
    ctx.reqs.add(app["requisition_id"])
    await recount_filled(app["requisition_id"])


async def w_candidates(ctx, d, body):
    ts = now_iso()
    refs = {k: v for k, v in {"source_id": await ctx.master("source", d.get("source")), "partner_id": await ctx.master("partner", d.get("partner")),
                               "recruiter_id": await ctx.master("recruiter", d.get("recruiter"))}.items() if v}
    result = "imported"
    if d.get("existing_id") and body.update_existing:
        await ctx.update("candidates", d["existing_id"], cand_fields(present(d, CAND_KEYS)) | refs | {"updated_at": ts})
        await ctx.log("import_update", "candidate", d["existing_id"], d.get("name"))
        cand = await db.candidates.find_one({"id": d["existing_id"]}, {"_id": 0})
        result = "updated"
    elif d.get("existing_id"):
        cand = await db.candidates.find_one({"id": d["existing_id"]}, {"_id": 0})
        result = "linked"
    else:
        cand = cand_fields(present(d, CAND_KEYS)) | refs | {
            "id": new_id(), "code": await unique_code("candidates", "CAN", 5, d.get("code")), "legacy_role": d.get("role"),
            "skills": [], "created_by": ctx.user["id"], "created_at": ts, "updated_at": ts, "import_source": ctx.source}
        await ctx.insert("candidates", cand)
        await ctx.log("import", "candidate", cand["id"], f"{cand['code']} {cand['name']}")
    apps = 0
    role = (d.get("role") or "").strip()
    if role:
        req = await db.requisitions.find_one({"title": {"$regex": f"^{re.escape(role)}$", "$options": "i"}, "status": {"$ne": "Cancelled"}}, {"_id": 0})
        if not req and body.create_missing_roles:
            await w_requisitions(ctx, {"title": role, "positions": 1, "remarks": "Auto-created during candidate import"}, body)
            req = await db.requisitions.find_one({"id": ctx.inserted[-1][1]}, {"_id": 0}) if ctx.inserted[-1][0] == "requisitions" else None
        if req and not await db.applications.find_one({"candidate_id": cand["id"], "requisition_id": req["id"]}):
            app = await create_app(ctx, cand["id"], req, d.get("status") or "New", d.get("remarks"), cand.get("recruiter_id"))
            apps = 1
            for rd in d.get("rounds", []):
                ivr = await ctx.master("interviewer", rd["interviewer"])
                st = {"Selected": "Completed", "Rejected": "Completed", "No Show": "No Show"}.get(rd["outcome"], "Scheduled")
                await ctx.insert("interviews", {"id": new_id(), "code": await unique_code("interviews", "INT"), "application_id": app["id"],
                                                "candidate_id": cand["id"], "requisition_id": req["id"], "round_number": rd["n"],
                                                "round_name": f"Round {rd['n']}", "date": rd["date"], "mode": None,
                                                "interviewer_ids": [ivr] if ivr else [], "status": st,
                                                "feedback_status": "Imported" if st == "Completed" else "Pending",
                                                "outcome": rd["outcome"] if rd["outcome"] != "No Show" else "Pending", "created_by": ctx.user["id"],
                                                "created_at": ts, "updated_at": ts, "import_source": ctx.source,
                                                "history": [{"at": ts, "by": ctx.user["name"], "action": "Imported", "details": ctx.source}]})
    return result, apps


async def w_applications(ctx, d, body):
    req = await db.requisitions.find_one({"id": d["requisition_id"]}, {"_id": 0})
    recruiter_id = await ctx.master("recruiter", d.get("recruiter"))
    if d.get("initiation_date") and not req.get("initiation_date"):
        await ctx.update("requisitions", req["id"], {"initiation_date": d["initiation_date"]})
    if d.get("existing_id"):
        app = await db.applications.find_one({"id": d["existing_id"]}, {"_id": 0})
        ts = now_iso()
        changes = {"updated_at": ts}
        if recruiter_id:
            changes["recruiter_id"] = recruiter_id
        if d["status"] != app["status"]:
            changes |= {"status": d["status"], "stage_entered_at": ts, "closed": d["status"] in INACTIVE,
                        "legacy_stage_index": max(app.get("legacy_stage_index", -1) if isinstance(app.get("legacy_stage_index"), int) else -1,
                                                  reached_index({"status": d["status"]})),
                        "history": app.get("history", []) + [{"status": d["status"], "from": app["status"], "at": ts, "by": ctx.user["name"],
                                                              "reason": d.get("remarks") or "", "auto": False, "note": "Updated by Excel import"}]}
        await ctx.update("applications", app["id"], changes)
        if d["status"] == "Joined":
            await upsert_joining(ctx, app | changes, d.get("actual_join_date"), d.get("remarks"))
        await ctx.log("import_update", "application", app["id"], f"{app['code']} → {d['status']}")
        return "updated"
    await create_app(ctx, d["candidate_id"], req, d["status"], d.get("remarks"), recruiter_id, d.get("application_date"), d.get("actual_join_date"))
    return "imported"


async def w_interviews(ctx, d, body):
    ts = now_iso()
    ivr = [await ctx.master("interviewer", n) for n in d.get("interviewer_names", [])]
    rt = await ctx.master("round_type", d.get("round_type"))
    has_fb = d.get("rating") is not None or d.get("feedback")
    fields = {"round_number": d["round_number"], "round_name": d.get("round_type") and f"{d['round_type']} Round" or f"Round {d['round_number']}",
              "round_type_id": rt, "date": d["date"], "start_time": d.get("start_time"), "end_time": d.get("end_time"), "mode": d.get("mode"),
              "interviewer_ids": ivr, "status": d["status"], "outcome": d["outcome"], "remarks": d.get("remarks"),
              "feedback_status": "Complete" if has_fb and ivr else ("Pending" if d["status"] != "Completed" else "Imported"), "updated_at": ts}
    if d.get("existing_id"):
        iid = d["existing_id"]
        await ctx.update("interviews", iid, fields)
        result = "updated"
    else:
        iid = new_id()
        await ctx.insert("interviews", fields | {"id": iid, "code": await unique_code("interviews", "INT"), "application_id": d["application_id"],
                                                 "candidate_id": d["candidate_id"], "requisition_id": d["requisition_id"], "location": None,
                                                 "created_by": ctx.user["id"], "created_at": ts, "import_source": ctx.source,
                                                 "history": [{"at": ts, "by": ctx.user["name"], "action": "Imported", "details": ctx.source}]})
        result = "imported"
    if has_fb and ivr and not await db.feedback.find_one({"interview_id": iid, "interviewer_id": ivr[0]}):
        scale = (await get_settings()).get("rating_scale", 5)
        rec = {"Selected": "Hire", "Rejected": "Reject", "On Hold": "Hold"}.get(d["outcome"], "Hold")
        await ctx.insert("feedback", {"id": new_id(), "interview_id": iid, "interviewer_id": ivr[0],
                                      "ratings": {"overall": d["rating"]} if d.get("rating") is not None else {}, "scale": scale,
                                      "recommendation": rec, "detailed": d.get("feedback") or "", "strengths": "", "improvements": "",
                                      "submitted_by": f"{ctx.user['name']} (import)", "submitted_at": ts})
    await ctx.log("import" if result == "imported" else "import_update", "interview", iid, f"Round {d['round_number']}")
    return result


async def w_costs(ctx, d, body):
    ts = now_iso()
    pid = None
    if d.get("partner"):
        contact = present({"contact_person": d.get("contact_person"), "email": d.get("contact_email"), "phone": d.get("contact_phone"),
                           "partner_type": d.get("partner_type")}, ("contact_person", "email", "phone", "partner_type"))
        pid = await ctx.master("partner", d["partner"], contact)
        m = await db.masters.find_one({"id": pid}, {"_id": 0})
        fill = {k: v for k, v in contact.items() if body.update_existing or not m.get(k)}
        if fill and not any(c == "masters" and i == pid for c, i in ctx.inserted):
            await ctx.update("masters", pid, fill)
    if not d["has_cost"]:
        return "imported"
    fields = {"category_id": await ctx.master("cost_category", d.get("category")), "partner_id": pid,
              "requisition_id": d.get("requisition_id"), "candidate_id": d.get("candidate_id"), "invoice_no": d.get("invoice_no"),
              "invoice_date": d.get("invoice_date"), "amount": d.get("amount"), "payment_status": d.get("payment_status") or "Pending",
              "payment_date": d.get("payment_date"), "remarks": d.get("remarks"), "updated_at": ts}
    if d.get("existing_id"):
        await ctx.update("costs", d["existing_id"], fields)
        await ctx.log("import_update", "cost", d["existing_id"], d.get("invoice_no") or "")
        return "updated"
    doc = await ctx.insert("costs", fields | {"id": new_id(), "code": await unique_code("costs", "CST"), "recruiter_id": None,
                                               "created_by": ctx.user["id"], "created_at": ts, "import_source": ctx.source})
    await ctx.log("import", "cost", doc["id"], f"{doc['code']} ₹{doc['amount']} L")
    return "imported"


WRITERS = {"requisitions": w_requisitions, "applications": w_applications, "interviews": w_interviews, "costs": w_costs}


@router.post("/commit")
async def commit(body: ValidateIn, user=Depends(require("import.run"))):
    b, s = await load(body)
    rows = await validate_rows(body, s)
    source = f"{b['filename']} / {s['name']}"
    ctx = Ctx(user, source, body.create_missing_masters)
    res = {"total": len(rows), "imported": 0, "updated": 0, "linked": 0, "applications": 0, "duplicates": 0,
           "skipped": 0, "failed": 0, "samples": 0}
    link_dups = body.type == "candidates" and not body.skip_duplicates
    try:
        for r in rows:
            st = r["status"]
            if st == "sample":
                res["samples"] += 1
                res["skipped"] += 1
                continue
            if st == "error":
                res["failed"] += 1
                continue
            if st == "duplicate" and not link_dups:
                res["duplicates"] += 1
                res["skipped"] += 1
                continue
            d = r["data"]
            if body.type == "interviewers":
                await ctx.insert("masters", {"id": new_id(), "type": "interviewer", "name": d["name"], "skill_area": d["skill_area"],
                                             "active": True, "user_id": None, "created_at": now_iso(), "notes": "Imported"})
                res["imported"] += 1
            elif body.type == "candidates":
                out, apps = await w_candidates(ctx, d, body)
                res[out] += 1
                res["applications"] += apps
                res["duplicates"] += out == "linked"
            else:
                res[await WRITERS[body.type](ctx, d, body)] += 1
    except Exception as e:
        await ctx.rollback()
        raise HTTPException(500, f"Import failed and was rolled back — no records were changed ({e})")
    await ctx.flush_logs()
    rejected = await store_report(b, s, body, rows, "import")
    res["rejected_count"] = rejected
    await db.import_batches.update_one({"id": b["id"]}, {"$set": {"result": res, "committed_at": now_iso(), "type": body.type}})
    await log_activity(user, "import_commit", "import", b["id"], source,
                       f"{body.type}: {res['imported']} new, {res['updated']} updated, {res['linked']} linked, "
                       f"{res['duplicates']} duplicates, {res['failed']} failed, {res['samples']} sample rows skipped")
    return res


@router.get("/{batch_id}/rejected")
async def rejected(batch_id: str, user=Depends(require("import.run"))):
    b = await db.import_batches.find_one({"id": batch_id}, {"_id": 0, "rejected": 1, "filename": 1})
    if not b or not b.get("rejected") or not b["rejected"]["rows"]:
        raise HTTPException(404, "No rejected rows for this import")
    rep = b["rejected"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Error Report"
    ws.append(rep["headers"])
    for c in ws[1]:
        c.font = Font(bold=True)
    red, amber = PatternFill("solid", fgColor="FECACA"), PatternFill("solid", fgColor="FDE68A")
    for r in rep["rows"]:
        values = r["values"] if isinstance(r, dict) else r
        ws.append(values)
        if isinstance(r, dict):
            ri = ws.max_row
            ws.cell(row=ri, column=2).fill = red if values[1] == "error" else amber
            for col in r.get("error_columns", []):
                if col in rep["headers"]:
                    ws.cell(row=ri, column=rep["headers"].index(col) + 1).fill = red
    ws.column_dimensions["C"].width = 70
    buf = io.BytesIO()
    wb.save(buf)
    return StreamingResponse(io.BytesIO(buf.getvalue()), media_type=XLSX,
                             headers={"Content-Disposition": f'attachment; filename="import-error-report-{today()}.xlsx"'})


@router.get("/history")
async def history(user=Depends(require("import.run"))):
    return await db.import_batches.find({"committed_at": {"$exists": True}}, {"_id": 0, "id": 1, "filename": 1, "uploaded_by": 1, "type": 1,
                                                                             "created_at": 1, "committed_at": 1, "result": 1}).sort("created_at", -1).to_list(50)
