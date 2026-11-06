import io
from datetime import date, datetime

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from core import (db, ALL_STATUSES, REQ_STATUSES, INTERVIEW_STATUSES, INTERVIEW_MODES, PAYMENT_STATUSES)

SAMPLE_TAG = "[SAMPLE]"
EITHER_OR = {"candidates": {"email", "phone"}}  # at least one of these is mandatory
PARTNER_TYPES = ["Consultancy", "Executive Search", "Freelance Recruiter", "Job Portal", "Other"]
OUTCOME_LIST = ["Pending", "Selected", "Rejected", "On Hold"]

# (header, field, required, kind, list_key, description)
TEMPLATES = {
    "requisitions": {"title": "Recruitment Requisitions", "sheet": "Requisitions", "columns": [
        ("Requisition ID", "code", False, "text", None, "Optional. Leave blank to auto-generate (e.g. REQ-0007). An ID that already exists is treated as a duplicate."),
        ("Job Title / Role", "title", True, "text", "job_title", "Role name. Must exist in Master Data → Job Titles unless 'create missing master data' is selected."),
        ("Department", "department", False, "list", "department", "Department / business function from master data."),
        ("Hiring Manager", "hiring_manager", False, "list", "hiring_manager", "Hiring manager name (or email) from master data."),
        ("Assigned Recruiter", "recruiter", False, "list", "recruiter", "Recruiter name (or email) from master data."),
        ("Number of Open Positions", "positions", True, "int", None, "Whole number, 1 or more."),
        ("Required Experience", "experience", False, "text", None, "Free text, e.g. 4-6 years."),
        ("Minimum CTC", "min_ctc", False, "num", None, "₹ in lakhs, e.g. 7.5"),
        ("Maximum CTC", "max_ctc", False, "num", None, "₹ in lakhs, must be ≥ Minimum CTC."),
        ("Preferred Location", "location", False, "list", "location", "Location from master data."),
        ("Required Skills", "skills", False, "text", None, "Comma separated, e.g. Java, Spring Boot"),
        ("Qualifications", "qualifications", False, "text", None, "Free text."),
        ("Employment Type", "employment_type", False, "list", "employment_type", "Employment type from master data."),
        ("CRF Raised Date", "crf_date", False, "date", None, "DD-MM-YYYY. Needed for Age per Hire — rows without it are flagged."),
        ("Recruitment Initiation Date", "initiation_date", False, "date", None, "DD-MM-YYYY. Stored separately; never overwrites the CRF date."),
        ("Priority", "priority", False, "list", "priority", "Priority level from master data."),
        ("Requisition Status", "status", False, "list", "req_status", "Draft, Open, On Hold, Closed or Cancelled. Blank = Open."),
        ("Remarks", "remarks", False, "text", None, "Free text."),
    ]},
    "candidates": {"title": "Candidate Master", "sheet": "Candidates", "columns": [
        ("Candidate ID", "code", False, "text", None, "Optional. Leave blank to auto-generate (e.g. CAN-00012)."),
        ("Full Name", "name", True, "text", None, "Candidate's full name."),
        ("Email", "email", False, "email", None, "Email OR Mobile Number is required. Used for duplicate detection."),
        ("Mobile Number", "phone", False, "text", None, "10-digit mobile. Email OR Mobile Number is required."),
        ("Current Company", "current_company", False, "text", None, ""),
        ("Current Designation", "current_designation", False, "text", None, ""),
        ("Current Location", "current_location", False, "text", None, "City."),
        ("Total Experience", "total_exp", False, "num", None, "Years, e.g. 5.5"),
        ("Relevant Experience", "relevant_exp", False, "num", None, "Years."),
        ("Educational Qualification", "qualification", False, "text", None, ""),
        ("Current CTC", "current_ctc", False, "num", None, "₹ in lakhs."),
        ("Expected CTC", "expected_ctc", False, "num", None, "₹ in lakhs."),
        ("Notice Period", "notice_period", False, "text", None, "e.g. 30 days, 2 months, Immediate."),
        ("Last Working Day", "last_working_day", False, "date", None, "DD-MM-YYYY, where applicable."),
        ("Available From", "available_from", False, "date", None, "DD-MM-YYYY."),
        ("Candidate Source", "source", False, "list", "source", "Source from master data (LinkedIn, Referral, Consultant…)."),
        ("Recruitment Partner / Consultancy", "partner", False, "list", "partner", "Partner from master data."),
        ("Assigned Recruiter", "recruiter", False, "list", "recruiter", "Recruiter name (or email) from master data."),
        ("Resume File Name / Resume Upload Reference", "resume_ref", False, "text", None, "File name or link for reference. Upload the actual CV on the candidate profile."),
        ("Remarks", "remarks", False, "text", None, ""),
    ]},
    "applications": {"title": "Candidate-Requisition Mapping", "sheet": "Applications", "columns": [
        ("Candidate ID or Candidate Email", "candidate_ref", True, "text", None, "Existing Candidate ID (CAN-…) or email. Import candidates first."),
        ("Requisition ID", "requisition_code", True, "text", None, "Existing Requisition ID (REQ-…)."),
        ("Assigned Recruiter", "recruiter", False, "list", "recruiter", "Recruiter for this application. Blank = requisition's recruiter."),
        ("Application Date", "application_date", False, "date", None, "DD-MM-YYYY. Blank = today."),
        ("Recruitment Initiation Date", "initiation_date", False, "date", None, "DD-MM-YYYY, if applicable. Set on the requisition only when it has none."),
        ("Current Application Status", "status", False, "list", "app_status", "Pipeline stage. Blank = New."),
        ("Actual Date of Joining", "actual_join_date", False, "date", None, "DD-MM-YYYY. Required when status is Joined (used for Age per Hire)."),
        ("Remarks", "remarks", False, "text", None, "Reason is required for rejected / withdrawn / on hold statuses."),
    ]},
    "interviews": {"title": "Interview Details", "sheet": "Interviews", "columns": [
        ("Candidate ID or Candidate Email", "candidate_ref", True, "text", None, "Existing Candidate ID or email."),
        ("Requisition ID", "requisition_code", True, "text", None, "Existing Requisition ID. The candidate must already be mapped to it."),
        ("Interview Round", "round_number", True, "int", None, "Round number: 1, 2, 3…"),
        ("Interview Type", "round_type", False, "list", "round_type", "Technical, HR, Managerial, Functional…"),
        ("Interview Date", "date", True, "date", None, "DD-MM-YYYY."),
        ("Start Time", "start_time", False, "time", None, "HH:MM (24-hour)."),
        ("End Time", "end_time", False, "time", None, "HH:MM (24-hour)."),
        ("Interview Mode", "mode", False, "list", "mode", "Online, In-Person or Phone."),
        ("Interviewer Name / Email", "interviewers", False, "list", "interviewer", "One or more interviewers from master data, separated by commas."),
        ("Interview Status", "status", False, "list", "iv_status", "Blank = Scheduled."),
        ("Interview Outcome", "outcome", False, "list", "outcome", "Pending, Selected, Rejected or On Hold."),
        ("Overall Rating", "rating", False, "num", None, "Number within the configured rating scale."),
        ("Feedback", "feedback", False, "text", None, "Interviewer feedback summary."),
        ("Remarks", "remarks", False, "text", None, ""),
    ]},
    "costs": {"title": "Recruitment Partners & Costs", "sheet": "Partners & Costs", "columns": [
        ("Recruitment Partner Name", "partner", False, "list", "partner", "New partners are added to master data. Leave blank for non-partner costs."),
        ("Partner Type", "partner_type", False, "list", "partner_type", ", ".join(PARTNER_TYPES)),
        ("Contact Person", "contact_person", False, "text", None, ""),
        ("Contact Email", "contact_email", False, "email", None, ""),
        ("Contact Number", "contact_phone", False, "text", None, ""),
        ("Cost Category", "category", True, "list", "cost_category", "Required for cost rows. Leave all cost columns blank to add a partner only."),
        ("Related Requisition ID", "requisition_code", False, "text", None, "Existing Requisition ID."),
        ("Candidate ID / Candidate Email", "candidate_ref", False, "text", None, "If the cost relates to a specific candidate."),
        ("Invoice Number", "invoice_no", False, "text", None, "Invoice number + partner identifies duplicates."),
        ("Invoice Date", "invoice_date", True, "date", None, "DD-MM-YYYY. Required for cost rows."),
        ("Amount", "amount", True, "num", None, "₹ in lakhs. Required for cost rows."),
        ("Payment Status", "payment_status", False, "list", "payment_status", "Pending, Partially Paid or Paid."),
        ("Payment Date", "payment_date", False, "date", None, "DD-MM-YYYY."),
        ("Remarks", "remarks", False, "text", None, ""),
    ]},
}

SAMPLES = {
    "requisitions": [["", "Java Developer", "Engineering", "Kewal", "Madhavi", 2, "4-6 years", 8, 14, "Pune", "Java, Spring Boot", "B.E. / B.Tech", "Full-time", "01-10-2026", "05-10-2026", "High", "Open"]],
    "candidates": [["", "Sample Candidate", "sample.candidate@example.com", "9800000000", "Acme Ltd", "Software Engineer", "Pune", 5, 4, "B.E.", 9.5, 13, "30 days", "", "01-12-2026", "LinkedIn", "", "Madhavi", "sample_cv.pdf"]],
    "applications": [["CAN-00001", "REQ-0001", "Madhavi", "10-10-2026", "", "Screening", ""]],
    "interviews": [["sample.candidate@example.com", "REQ-0001", 1, "Technical", "15-10-2026", "11:00", "12:00", "Online", "Arpita", "Completed", "Selected", 4, "Strong core Java"]],
    "costs": [["BrainsTerra", "Consultancy", "Contact Name", "contact@example.com", "9800000001", "Recruitment Partner / Consultancy Fees", "REQ-0001", "CAN-00001", "INV-001", "31-10-2026", 1.2, "Pending", ""]],
}


async def list_values():
    masters = {}
    async for m in db.masters.find({"active": True}, {"_id": 0, "type": 1, "name": 1}):
        masters.setdefault(m["type"], []).append(m["name"])
    return masters | {"req_status": REQ_STATUSES, "app_status": ALL_STATUSES, "iv_status": INTERVIEW_STATUSES,
                      "mode": INTERVIEW_MODES, "payment_status": PAYMENT_STATUSES, "outcome": OUTCOME_LIST,
                      "partner_type": PARTNER_TYPES}


async def build_template(key):
    t = TEMPLATES[key]
    values = await list_values()
    wb = Workbook()
    ws = wb.active
    ws.title = t["sheet"]
    lists = wb.create_sheet("Lists")
    req_fill, opt_fill = PatternFill("solid", fgColor="18181B"), PatternFill("solid", fgColor="E4E4E7")
    either_fill = PatternFill("solid", fgColor="B45309")
    either = EITHER_OR.get(key, set())
    sample_fill = PatternFill("solid", fgColor="FEF3C7")
    list_col = 0
    for ci, (head, field, req, kind, lkey, desc) in enumerate(t["columns"], start=1):
        c = ws.cell(row=1, column=ci, value=f"{head}*" if req else f"{head}†" if field in either else head)
        if req:
            c.fill, c.font = req_fill, Font(bold=True, color="FFFFFF")
        elif field in either:
            c.fill, c.font = either_fill, Font(bold=True, color="FFFFFF")
        else:
            c.fill, c.font = opt_fill, Font(bold=True, color="18181B")
        c.alignment = Alignment(wrap_text=True, vertical="center")
        c.comment = Comment(("MANDATORY. " if req else "") + desc, "MMS Portal")
        letter = get_column_letter(ci)
        ws.column_dimensions[letter].width = max(16, min(36, len(head) + 4))
        rng = f"{letter}2:{letter}2000"
        dv = None
        if kind == "date":
            dv = DataValidation(type="date", operator="between", formula1="DATE(1990,1,1)", formula2="DATE(2100,12,31)",
                                error="Enter a date as DD-MM-YYYY", errorTitle="Invalid date", showErrorMessage=True)
            for r in range(2, 2001):
                ws.cell(row=r, column=ci).number_format = "DD-MM-YYYY"
        elif kind == "int":
            dv = DataValidation(type="whole", operator="greaterThanOrEqual", formula1="0", error="Enter a whole number", showErrorMessage=True)
        elif kind == "num":
            dv = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0", error="Enter a number (0 or more)", showErrorMessage=True)
        elif kind == "email":
            dv = DataValidation(type="custom", formula1=f'OR(ISBLANK({letter}2),ISNUMBER(SEARCH("@",{letter}2)))', error="Enter a valid email address", showErrorMessage=True)
        elif field in ("phone", "contact_phone"):
            dv = DataValidation(type="textLength", operator="between", formula1="10", formula2="15",
                                error="Enter a 10-digit mobile number (country code allowed)", errorTitle="Invalid mobile number", showErrorMessage=True)
            for r in range(2, 2001):
                ws.cell(row=r, column=ci).number_format = "@"
        elif kind == "time":
            dv = DataValidation(type="time", operator="between", formula1="0", formula2="0.999988", error="Enter time as HH:MM", showErrorMessage=True)
            for r in range(2, 2001):
                ws.cell(row=r, column=ci).number_format = "HH:MM"
        elif lkey:
            opts = values.get(lkey, [])
            list_col += 1
            ll = get_column_letter(list_col)
            lists.cell(row=1, column=list_col, value=head)
            for ri, o in enumerate(opts, start=2):
                lists.cell(row=ri, column=list_col, value=o)
            if opts:
                strict = lkey in ("req_status", "app_status", "iv_status", "mode", "payment_status", "outcome")
                dv = DataValidation(type="list", formula1=f"=Lists!${ll}$2:${ll}${len(opts) + 1}", showDropDown=False,
                                    showErrorMessage=strict, errorStyle="stop" if strict else "warning",
                                    error="Choose a value from the list", errorTitle="Not in list")
        if dv:
            ws.add_data_validation(dv)
            dv.add(rng)
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 34
    ncol = len(t["columns"])
    for ri, sample in enumerate(SAMPLES[key], start=2):
        row = list(sample) + [""] * (ncol - len(sample))
        row[ncol - 1] = f"{SAMPLE_TAG} Example row — ignored on import. Delete this row before adding your data."
        kinds = [c[3] for c in t["columns"]]
        for ci, v in enumerate(row, start=1):
            if kinds[ci - 1] == "date" and isinstance(v, str) and v:
                v = datetime.strptime(v, "%d-%m-%Y")
            elif kinds[ci - 1] == "time" and isinstance(v, str) and v:
                v = datetime.strptime(v, "%H:%M").time()
            elif ci <= len(kinds) and t["columns"][ci - 1][1] in ("phone", "contact_phone") and v:
                v = str(v)
            cell = ws.cell(row=ri, column=ci, value=v if v != "" else None)
            cell.fill, cell.font = sample_fill, Font(italic=True, color="92400E")
    lists.sheet_state = "hidden"

    ins = wb.create_sheet("Instructions", 0)
    ins.column_dimensions["A"].width, ins.column_dimensions["B"].width = 42, 12
    ins.column_dimensions["C"].width, ins.column_dimensions["D"].width = 22, 90
    ins.append([f"MMS Recruitment Portal — {t['title']} import template"])
    ins["A1"].font = Font(bold=True, size=14)
    for line in (f"1. Fill your data in the '{t['sheet']}' sheet, starting from row 2. Do not rename the sheet or the column headers.",
                 "2. Columns with a black header and * are mandatory. Grey headers are optional."
                 + (" Amber headers marked † are 'either/or': at least one of them must be filled." if EITHER_OR.get(key) else ""),
                 "3. Dates must be DD-MM-YYYY (e.g. 05-11-2026). Amounts are ₹ in lakhs (e.g. 12.5 = ₹12.5 L).",
                 "4. Use the dropdowns where provided. Values must match the portal's master data.",
                 f"5. Yellow rows tagged {SAMPLE_TAG} in the Remarks column are examples and are never imported. Delete them before adding your data "
                 f"(if you reuse a sample row, also clear the {SAMPLE_TAG} text in Remarks, or the row will be skipped).",
                 "6. Upload the file under Data Import & Migration. You will see a preview and row-level errors before anything is saved.",
                 "7. Existing records are never overwritten unless you explicitly choose 'Update existing records'."):
        ins.append([line])
    ins.append([])
    ins.append(["Column", "Mandatory", "Format", "Description / allowed values"])
    for c in ins[ins.max_row]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), req_fill
    fmt = {"text": "Text", "list": "Dropdown", "date": "DD-MM-YYYY", "int": "Whole number", "num": "Number", "email": "Email", "time": "HH:MM"}
    for head, field, req, kind, lkey, desc in t["columns"]:
        allowed = values.get(lkey, []) if lkey else []
        extra = f" Allowed: {', '.join(allowed[:25])}{'…' if len(allowed) > 25 else ''}" if allowed else ""
        mand = "Yes" if req else "Either/or" if field in either else "No"
        ins.append([head, mand, "10-digit mobile" if field in ("phone", "contact_phone") else fmt[kind], desc + extra])
        ins.cell(row=ins.max_row, column=4).alignment = Alignment(wrap_text=True)
    wb.active = 0
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), f"MMS-{t['sheet'].replace(' & ', '-').replace(' ', '-')}-Template-{date.today().isoformat()}.xlsx"
