import { useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { FormDialog, SelectField } from "@/components/common/FormDialog";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { useAuth } from "@/context/AuthContext";
import { api, errMsg } from "@/lib/api";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { StageWizard } from "@/components/StageWizard";

const opts = (arr) => arr.map((s) => ({ value: s, label: s }));

export const reqFields = (meta) => [
  { name: "title", label: "Job Title / Role", required: true, suggest: "job_title" },
  { name: "department_name", label: "Department / Business Function", suggest: "department", placeholder: "Type the department" },
  { name: "hiring_manager_name", label: "Hiring Manager", suggest: "hiring_manager", placeholder: "Type the hiring manager's name" },
  { name: "recruiter_id", label: "Assigned Recruiter", master: "recruiter" },
  { name: "positions", label: "Number of Open Positions", type: "number", required: true, min: 1 },
  { name: "interview_rounds_required", label: "Interview Rounds Required", type: "number", min: 1, help: "Completed rounds (with all feedback) needed before selection. Blank = 1." },
  { name: "experience", label: "Required Experience", placeholder: "e.g. 4-6 years" },
  { name: "min_ctc", label: "Minimum CTC (₹ L)", type: "number" },
  { name: "max_ctc", label: "Maximum CTC (₹ L)", type: "number" },
  { name: "location_name", label: "Preferred Location", type: "select", options: opts(["Mumbai", "Pune"]) },
  { name: "employment_type_id", label: "Employment Type", master: "employment_type" },
  { name: "priority_id", label: "Priority", master: "priority" },
  { name: "status", label: "Status", type: "select", options: opts(meta.req_statuses), default: "Open" },
  { name: "crf_date", label: "CRF Raised Date", type: "date" },
  { name: "initiation_date", label: "Recruitment Initiation Date", type: "date" },
  { name: "skills", label: "Required Skills", placeholder: "Comma separated", full: true },
  { name: "qualifications", label: "Qualifications", full: true },
  { name: "remarks", label: "Remarks", type: "textarea" },
  { name: "closure_reason", label: "Closure Reason (if closing with unfilled positions)", type: "textarea" },
];

export const candFields = () => [
  { name: "name", label: "Full Name", required: true },
  { name: "email", label: "Email", type: "email" },
  { name: "phone", label: "Mobile Number" },
  { name: "current_company", label: "Current Company" },
  { name: "current_designation", label: "Current Designation" },
  { name: "current_location", label: "Current Location", suggest: "location" },
  { name: "total_exp", label: "Total Experience (yrs)", type: "number" },
  { name: "relevant_exp", label: "Relevant Experience (yrs)", type: "number" },
  { name: "qualification", label: "Educational Qualification" },
  { name: "notice_period", label: "Notice Period", placeholder: "e.g. 30 days, Immediate" },
  { name: "current_ctc", label: "Current CTC (₹ L)", type: "number" },
  { name: "expected_ctc", label: "Expected CTC (₹ L)", type: "number" },
  { name: "last_working_day", label: "Last Working Day", type: "date" },
  { name: "available_from", label: "Available From", type: "date" },
  { name: "source_id", label: "Candidate Source", master: "source" },
  { name: "partner_name", label: "Recruitment Partner / Consultancy", suggest: "partner", placeholder: "Type the consultancy name" },
  { name: "recruiter_id", label: "Assigned Recruiter", master: "recruiter" },
  { name: "remarks", label: "Remarks", type: "textarea" },
];

export const toSkills = (v) => (typeof v === "string" ? v.split(",").map((s) => s.trim()).filter(Boolean) : v || []);

export function CandidateDialog({ open, onOpenChange, initial, onSaved, extraFields = [] }) {
  const [dups, setDups] = useState(null);
  const [pending, setPending] = useState(null);
  const save = async (vals, force = false) => {
    try {
      const body = { ...vals, force };
      const r = initial?.id ? await api.put(`/candidates/${initial.id}`, body) : await api.post("/candidates", body);
      toast.success(initial?.id ? "Candidate updated" : "Candidate created");
      setDups(null);
      onOpenChange(false);
      onSaved?.(r.data);
    } catch (e) {
      if (e.response?.status === 409 && e.response.data?.detail?.duplicates) {
        setDups(e.response.data.detail.duplicates);
        setPending(vals);
      } else toast.error(errMsg(e));
    }
  };
  return (
    <FormDialog open={open} onOpenChange={(o) => { setDups(null); onOpenChange(o); }} title={initial?.id ? "Edit candidate" : "Add candidate"} wide
      fields={[...candFields(), ...extraFields]} initial={initial ? { ...initial, partner_name: initial.partner || "" } : initial} onSubmit={(v) => save(v)} testid="candidate-form">
      {dups && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900" data-testid="duplicate-warning">
          <p className="flex items-center gap-2 font-semibold"><AlertTriangle className="h-4 w-4" />Potential duplicate candidate</p>
          <ul className="mt-1 list-disc pl-5 text-xs">{dups.map((d) => <li key={d.id}>{d.code} · {d.name} · {d.email || "—"} · {d.phone || "—"}</li>)}</ul>
          <Button type="button" size="sm" variant="outline" className="mt-2" onClick={() => save(pending, true)} data-testid="duplicate-save-anyway">Save anyway</Button>
        </div>
      )}
    </FormDialog>
  );
}

export function ScheduleDialog({ open, onOpenChange, application, onDone }) {
  const { meta } = useAuth();
  const [clash, setClash] = useState(null);
  const [pending, setPending] = useState(null);
  const fields = [
    { name: "round_name", label: "Round Name", required: true, placeholder: "e.g. Technical Round 1" },
    { name: "round_type_id", label: "Interview Type", master: "round_type" },
    { name: "date", label: "Interview Date", type: "date", required: true },
    { name: "mode", label: "Interview Mode", type: "select", options: opts(meta.interview_modes), default: "Online" },
    { name: "start_time", label: "Start Time", type: "time" },
    { name: "end_time", label: "End Time", type: "time" },
    { name: "interviewer_ids", label: "Interviewer(s)", type: "multi", master: "interviewer", required: true, full: true },
    { name: "location", label: "Meeting Link / Location", full: true },
    { name: "remarks", label: "Remarks", type: "textarea" },
  ];
  const save = async (vals, force = false) => {
    try {
      await api.post("/interviews", { ...vals, application_id: application.id, force });
      toast.success("Interview scheduled");
      setClash(null);
      onOpenChange(false);
      onDone?.();
    } catch (e) {
      if (e.response?.status === 409 && e.response.data?.detail?.conflicts) { setClash(e.response.data.detail.conflicts); setPending(vals); } else toast.error(errMsg(e));
    }
  };
  return (
    <FormDialog open={open} onOpenChange={(o) => { setClash(null); onOpenChange(o); }} title="Schedule interview" wide
      description={application ? `${application.candidate_name} · ${application.requisition_title}` : ""} fields={fields} onSubmit={(v) => save(v)} testid="schedule-form" submitLabel="Schedule">
      {clash && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900" data-testid="conflict-warning">
          <p className="flex items-center gap-2 font-semibold"><AlertTriangle className="h-4 w-4" />Schedule conflict</p>
          <ul className="mt-1 list-disc pl-5 text-xs">{clash.map((c, i) => <li key={i}>{c}</li>)}</ul>
          <Button type="button" size="sm" variant="outline" className="mt-2" onClick={() => save(pending, true)} data-testid="conflict-schedule-anyway">Schedule anyway</Button>
        </div>
      )}
    </FormDialog>
  );
}

const RATINGS = [["technical", "Technical / Functional Knowledge"], ["communication", "Communication"], ["problem_solving", "Problem Solving"],
  ["relevant_experience", "Relevant Experience"], ["role_fit", "Role Fit"], ["overall", "Overall Rating"]];

export function FeedbackDialog({ open, onOpenChange, interview, onDone }) {
  const { meta, user, mname } = useAuth();
  const scale = meta.settings.rating_scale || 5;
  const [r, setR] = useState({});
  const [rec, setRec] = useState(null);
  const [text, setText] = useState({ detailed: "", strengths: "", improvements: "" });
  const [ivr, setIvr] = useState(null);
  const [busy, setBusy] = useState(false);
  const admin = ["super_admin", "recruiter"].includes(user.role);
  const ready = RATINGS.every(([k]) => r[k]) && rec && text.detailed.trim() && (!admin || ivr || interview?.my_pending?.length);
  const submit = async () => {
    setBusy(true);
    try {
      await api.post(`/interviews/${interview.id}/feedback`, { ratings: r, recommendation: rec, ...text, interviewer_id: admin ? ivr : null });
      toast.success("Feedback submitted");
      setR({}); setRec(null); setText({ detailed: "", strengths: "", improvements: "" });
      onOpenChange(false);
      onDone?.();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  if (!interview) return null;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl" data-testid="feedback-dialog">
        <DialogHeader><DialogTitle>Interview feedback · {interview.candidate_name}</DialogTitle>
          <p className="text-xs text-zinc-500">{interview.code} · Round {interview.round_number} {interview.round_name} · Scale 1–{scale}</p></DialogHeader>
        {admin && (
          <div className="space-y-1.5"><Label className="text-xs">Submitting on behalf of</Label>
            <SelectField value={ivr} onChange={setIvr} options={interview.interviewer_ids.map((i) => ({ value: i, label: mname(i) || i }))} testid="feedback-interviewer" placeholder="Select interviewer" /></div>
        )}
        <div className="space-y-3">
          {RATINGS.map(([k, label]) => (
            <div key={k} className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-zinc-700">{label}</p>
              <div className="flex gap-1">
                {[...Array(scale)].map((_, i) => (
                  <button type="button" key={i} onClick={() => setR({ ...r, [k]: i + 1 })} data-testid={`rating-${k}-${i + 1}`}
                    className={cn("h-8 w-8 rounded-md border text-xs font-semibold transition-colors", r[k] >= i + 1 ? "border-[#18181B] bg-[#18181B] text-white" : "border-zinc-200 hover:border-zinc-400")}>{i + 1}</button>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="space-y-1.5"><Label className="text-xs">Recommendation *</Label>
          <div className="flex flex-wrap gap-2">{meta.recommendations.map((x) => (
            <button type="button" key={x} onClick={() => setRec(x)} data-testid={`recommend-${x.toLowerCase().replace(" ", "-")}`}
              className={cn("rounded-full border px-3 py-1 text-xs font-semibold", rec === x ? "border-[#18181B] bg-[#18181B] text-white" : "border-zinc-200")}>{x}</button>))}</div></div>
        {[["detailed", "Detailed Feedback *"], ["strengths", "Strengths"], ["improvements", "Areas of Improvement"]].map(([k, l]) => (
          <div key={k} className="space-y-1.5"><Label className="text-xs">{l}</Label><Textarea rows={k === "detailed" ? 4 : 2} value={text[k]} onChange={(e) => setText({ ...text, [k]: e.target.value })} data-testid={`feedback-${k}`} /></div>
        ))}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button disabled={!ready || busy} onClick={submit} data-testid="feedback-submit">{busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Submit feedback</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function MoveDialog({ move, onClose, onDone }) {
  const { meta } = useAuth();
  if (!move) return null;
  const terminal = meta.terminal.includes(move.status);
  // every move into a pipeline stage goes through the guided wizard, which checks (and lets the user complete) the earlier stages
  if (!terminal) return <StageWizard app={move.app} target={move.status} focus={move.focus} open={!!move} onClose={onClose} onDone={onDone} />;
  return (
    <ConfirmDialog open={!!move} onOpenChange={(o) => !o && onClose()} title={`Move to "${move.status}"`} testid="move"
      description={`${move.app.candidate_name} · ${move.app.requisition_title} (currently ${move.app.status})`} reason
      reasonLabel={`Reason for ${move.status.toLowerCase()}`} confirmLabel="Update stage" destructive
      onConfirm={async ({ reason, date }) => {
        try {
          await api.post(`/applications/${move.app.id}/status`, { status: move.status, reason, joining_date: date });
          toast.success("Stage updated");
          onDone?.();
        } catch (e) { toast.error(errMsg(e)); throw e; }
      }} />
  );
}

export function SelectionDialog({ open, onOpenChange, app, onDone }) {
  const { user } = useAuth();
  const fields = [
    { name: "decision", label: "Final Decision", type: "select", options: opts(["Selected", "Rejected", "On Hold"]), required: true, allowNone: false },
    { name: "decision_maker", label: "Decision Maker", required: true },
    { name: "selection_date", label: "Selection Date", type: "date", required: true, max: new Date().toISOString().slice(0, 10) },
    { name: "compensation", label: "Selected Compensation (₹ L) — required when Selected", type: "number" },
    { name: "approval_status", label: "Approval Status", type: "select", options: opts(["Pending", "Approved", "Rejected"]), default: "Pending" },
    { name: "remarks", label: "Remarks (required for reject / hold)", type: "textarea" },
    ...(user.role === "super_admin" ? [{ name: "override_reason", label: "Exception — select without the required interviews (Super Admin, reason)", type: "textarea", full: true,
      help: "Leave blank for a normal selection. Filled in, it records an audited interview waiver." }] : []),
  ];
  return (
    <FormDialog open={open} onOpenChange={onOpenChange} title="Record selection decision" description={app ? `${app.candidate_name} · ${app.requisition_title}` : ""} wide
      fields={fields} initial={{ decision: "Selected", decision_maker: user.name, selection_date: new Date().toISOString().slice(0, 10), approval_status: "Pending" }} testid="selection-form" submitLabel="Record decision"
      onSubmit={async (v) => { try { await api.post("/selections", { ...v, application_id: app.id }); toast.success("Decision recorded"); onOpenChange(false); onDone?.(); } catch (e) { toast.error(errMsg(e)); } }} />
  );
}

export function OfferDialog({ open, onOpenChange, app, offer, onDone }) {
  const fields = [
    { name: "designation", label: "Offered Designation", required: true },
    { name: "ctc", label: "Offered CTC (₹ L)", type: "number", required: true },
    { name: "fixed", label: "Fixed (₹ L)", type: "number" },
    { name: "variable", label: "Variable (₹ L)", type: "number" },
    { name: "other", label: "Other / Joining Bonus (₹ L)", type: "number" },
    { name: "validity_date", label: "Offer Validity Date", type: "date", required: true },
    { name: "remarks", label: "Remarks", type: "textarea" },
  ];
  return (
    <FormDialog open={open} onOpenChange={onOpenChange} title={offer ? `Edit offer ${offer.code}` : "Create offer"} description={app ? `${app.candidate_name} · ${app.requisition_title}` : ""} wide
      fields={fields} initial={offer || { designation: app?.requisition_title }} testid="offer-form" submitLabel={offer ? "Save" : "Create draft offer"}
      onSubmit={async (v) => {
        try {
          if (offer) await api.put(`/offers/${offer.id}`, v); else await api.post("/offers", { ...v, application_id: app.id });
          toast.success(offer ? "Offer updated" : "Draft offer created"); onOpenChange(false); onDone?.();
        } catch (e) { toast.error(errMsg(e)); }
      }} />
  );
}
