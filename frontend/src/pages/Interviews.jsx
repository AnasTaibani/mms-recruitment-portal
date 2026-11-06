import { useState } from "react";
import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useAuth } from "@/context/AuthContext";
import { useFetch } from "@/lib/useFetch";
import { Info, PageHeader, Timeline } from "@/components/common/Page";
import { DataTable } from "@/components/common/DataTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { FormDialog, SelectField } from "@/components/common/FormDialog";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { FeedbackDialog } from "@/components/forms";
import { api, download, errMsg, fmtDate, fmtDateTime } from "@/lib/api";
import { toast } from "sonner";

const RLABEL = { technical: "Technical", communication: "Communication", problem_solving: "Problem solving", relevant_experience: "Relevant exp.", role_fit: "Role fit", overall: "Overall" };

function Detail({ id, onClose, onChanged }) {
  const { can, user } = useAuth();
  const { data: iv, reload } = useFetch(id ? `/interviews/${id}` : null, {}, !!id);
  const [dlg, setDlg] = useState(null);
  const refresh = () => { reload(); onChanged(); };
  const status = async (body, msg) => { try { await api.post(`/interviews/${id}/status`, body); toast.success(msg); refresh(); } catch (e) { toast.error(errMsg(e)); throw e; } };
  const open = iv && ["Scheduled", "Rescheduled"].includes(iv.status);
  const canFb = iv && can("feedback.submit") && !["Cancelled", "No Show"].includes(iv.status) && (iv.my_pending.length || ["super_admin", "hr_admin"].includes(user.role) || iv.feedback.some((f) => iv.interviewer_ids.includes(f.interviewer_id)));
  return (
    <Sheet open={!!id} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl" data-testid="interview-detail">
        {!iv ? <p className="text-sm text-zinc-400">Loading…</p> : <>
          <SheetHeader><p className="font-mono text-[11px] text-zinc-400">{iv.code}</p><SheetTitle>{iv.candidate_name} · Round {iv.round_number}</SheetTitle>
            <p className="text-sm text-zinc-500">{iv.round_name} · {iv.requisition_title}</p></SheetHeader>
          <div className="my-4 flex flex-wrap gap-2"><StatusBadge status={iv.status} testid="iv-status" /><StatusBadge status={`Feedback ${iv.feedback_status}`} tone="zinc" /><StatusBadge status={iv.outcome} testid="iv-outcome" /></div>
          <div className="grid grid-cols-2 gap-4">
            <Info label="Date">{fmtDate(iv.date)}</Info><Info label="Time">{iv.start_time ? `${iv.start_time} – ${iv.end_time || ""}` : null}</Info>
            <Info label="Mode">{iv.mode}</Info><Info label="Type">{iv.round_type}</Info>
            <div className="col-span-2"><Info label="Interviewers">{iv.interviewers.filter(Boolean).join(", ")}</Info></div>
            <div className="col-span-2"><Info label="Link / location">{iv.location}</Info></div>
            {iv.remarks && <div className="col-span-2"><Info label="Remarks">{iv.remarks}</Info></div>}
          </div>
          <div className="my-5 flex flex-wrap gap-2">
            {canFb && <Button size="sm" onClick={() => setDlg("fb")} data-testid="iv-feedback-btn">Submit feedback</Button>}
            {can("interview.manage") && open && <>
              <Button size="sm" variant="outline" onClick={() => setDlg("resched")} data-testid="iv-reschedule-btn">Reschedule</Button>
              <Button size="sm" variant="outline" onClick={() => status({ status: "Completed" }, "Marked completed")} data-testid="iv-complete-btn">Mark completed</Button>
              <Button size="sm" variant="outline" onClick={() => setDlg("noshow")} data-testid="iv-noshow-btn">No show</Button>
              <Button size="sm" variant="outline" className="text-rose-700" onClick={() => setDlg("cancel")} data-testid="iv-cancel-btn">Cancel</Button></>}
            {(can("interview.manage") || can("selection.decide")) && iv.status !== "Cancelled" && (
              <SelectField value={null} onChange={(v) => v && status({ outcome: v }, `Outcome set to ${v}`)} options={["Selected", "Rejected", "On Hold", "Pending"].map((s) => ({ value: s, label: s }))} placeholder="Set outcome…" testid="iv-outcome-select" className="w-36" />)}
          </div>
          <h4 className="eyebrow mb-2">Feedback ({iv.feedback.length}/{iv.interviewer_ids.length})</h4>
          {!iv.feedback.length && <p className="text-sm text-zinc-400">No feedback submitted yet.</p>}
          {iv.feedback.map((f) => (
            <div key={f.interviewer_id} className="mb-3 rounded-lg border border-zinc-200 p-3" data-testid="feedback-card">
              <div className="flex items-center justify-between"><p className="text-sm font-semibold">{f.interviewer}</p><StatusBadge status={f.recommendation} /></div>
              <div className="mt-2 grid grid-cols-3 gap-2">{Object.entries(f.ratings).map(([k, v]) => <div key={k} className="text-xs"><span className="text-zinc-500">{RLABEL[k]}</span> <b>{v}/{f.scale}</b></div>)}</div>
              <p className="mt-2 text-sm text-zinc-700">{f.detailed}</p>
              {f.strengths && <p className="mt-1 text-xs"><b>Strengths:</b> {f.strengths}</p>}
              {f.improvements && <p className="text-xs"><b>Improve:</b> {f.improvements}</p>}
              <p className="mt-1 text-[10px] text-zinc-400">{f.submitted_by} · {fmtDateTime(f.submitted_at)}</p>
            </div>))}
          <h4 className="eyebrow mb-2 mt-5">History</h4>
          <Timeline items={[...(iv.history || [])].reverse().map((h) => ({ title: h.action, details: h.details, meta: `${h.by} · ${fmtDateTime(h.at)}` }))} />
          <FeedbackDialog open={dlg === "fb"} onOpenChange={(o) => !o && setDlg(null)} interview={iv} onDone={refresh} />
          <FormDialog open={dlg === "resched"} onOpenChange={(o) => !o && setDlg(null)} title="Reschedule interview" testid="resched-form" submitLabel="Reschedule"
            fields={[{ name: "date", label: "New date", type: "date", required: true }, { name: "start_time", label: "Start", type: "time" }, { name: "end_time", label: "End", type: "time" }, { name: "reason", label: "Reason", type: "textarea", required: true }]}
            initial={{ date: iv.date, start_time: iv.start_time, end_time: iv.end_time }}
            onSubmit={async (v) => { try { await api.post(`/interviews/${id}/reschedule`, { ...v, force: true }); toast.success("Rescheduled"); setDlg(null); refresh(); } catch (e) { toast.error(errMsg(e)); } }} />
          <ConfirmDialog open={dlg === "cancel"} onOpenChange={(o) => !o && setDlg(null)} title="Cancel interview?" reason destructive confirmLabel="Cancel interview" testid="iv-cancel" onConfirm={({ reason }) => status({ status: "Cancelled", reason }, "Interview cancelled")} />
          <ConfirmDialog open={dlg === "noshow"} onOpenChange={(o) => !o && setDlg(null)} title="Mark as no show?" description="The application will move to No Show." reason destructive confirmLabel="Mark no show" testid="iv-noshow" onConfirm={({ reason }) => status({ status: "No Show", reason }, "Marked no show")} />
        </>}
      </SheetContent>
    </Sheet>
  );
}

export default function Interviews() {
  const { meta, list, can, user } = useAuth();
  const [f, setF] = useState({ mine: user.role === "interviewer" ? "true" : "" });
  const [sel, setSel] = useState(null);
  const { data, loading, reload } = useFetch("/interviews", f);
  const cols = [
    { key: "code", label: "ID", render: (i) => <span className="font-mono text-xs">{i.code}</span> },
    { key: "candidate_name", label: "Candidate", render: (i) => <span className="font-medium text-zinc-900">{i.candidate_name}</span> },
    { key: "requisition_title", label: "Role" },
    { key: "round_number", label: "Round", render: (i) => `R${i.round_number} · ${i.round_name}` },
    { key: "round_type", label: "Type" },
    { key: "date", label: "Date", render: (i) => fmtDate(i.date) },
    { key: "start_time", label: "Time", render: (i) => (i.start_time ? `${i.start_time}–${i.end_time || ""}` : "—") },
    { key: "mode", label: "Mode" },
    { key: "interviewers", label: "Interviewers", value: (i) => i.interviewers.filter(Boolean).join(", ") },
    { key: "status", label: "Status", render: (i) => <StatusBadge status={i.status} /> },
    { key: "feedback_status", label: "Feedback", render: (i) => <span className="text-xs">{i.feedback_count}/{i.interviewer_ids.length} {i.my_pending.length > 0 && <b className="text-amber-700">· yours pending</b>}</span> },
    { key: "outcome", label: "Outcome", render: (i) => <StatusBadge status={i.outcome} /> },
  ];
  return (
    <div>
      <PageHeader eyebrow="Recruitment" title="Interviews" description="Dynamic rounds per application, with feedback recorded separately for each interviewer."
        actions={can("reports.export") && <Button variant="outline" onClick={() => download("/reports/interviews", f)} data-testid="iv-export-btn"><Download className="mr-2 h-4 w-4" />Export schedule</Button>} />
      <DataTable testid="iv-table" columns={cols} data={data} loading={loading} onRowClick={(i) => setSel(i.id)} emptyHint="Schedule interviews from the pipeline or a candidate's application."
        toolbar={<>
          <SelectField value={f.status} onChange={(v) => setF({ ...f, status: v })} options={meta.interview_statuses.map((s) => ({ value: s, label: s }))} placeholder="All statuses" testid="iv-filter-status" className="w-36" />
          {user.role !== "interviewer" && <SelectField value={f.interviewer_id} onChange={(v) => setF({ ...f, interviewer_id: v })} options={list("interviewer").map((m) => ({ value: m.id, label: m.name }))} placeholder="All interviewers" testid="iv-filter-interviewer" className="w-40" />}
          <SelectField value={f.feedback_status} onChange={(v) => setF({ ...f, feedback_status: v })} options={["Pending", "Partial", "Complete"].map((s) => ({ value: s, label: `Feedback ${s}` }))} placeholder="Any feedback" testid="iv-filter-feedback" className="w-40" />
          <input type="date" className="h-9 rounded-md border px-2 text-xs" value={f.date_from || ""} onChange={(e) => setF({ ...f, date_from: e.target.value })} data-testid="iv-filter-from" />
          <input type="date" className="h-9 rounded-md border px-2 text-xs" value={f.date_to || ""} onChange={(e) => setF({ ...f, date_to: e.target.value })} data-testid="iv-filter-to" />
          {user.role !== "interviewer" && <label className="flex items-center gap-2 text-xs text-zinc-600"><Switch checked={f.mine === "true"} onCheckedChange={(c) => setF({ ...f, mine: c ? "true" : "" })} data-testid="iv-filter-mine" />Mine only</label>}
        </>} />
      <Detail id={sel} onClose={() => setSel(null)} onChanged={reload} />
    </div>
  );
}
