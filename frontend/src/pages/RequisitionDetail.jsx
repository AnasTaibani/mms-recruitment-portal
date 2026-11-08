import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Pencil, UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";
import { useAuth } from "@/context/AuthContext";
import { useFetch } from "@/lib/useFetch";
import { Info, PageHeader, Section, Timeline } from "@/components/common/Page";
import { DataTable } from "@/components/common/DataTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { FormDialog } from "@/components/common/FormDialog";
import { AppActions } from "@/components/AppActions";
import { CandidateDialog } from "@/components/forms";
import { ReqForm } from "@/pages/Requisitions";
import { api, errMsg, fmtDate, fmtDateTime, lakhs } from "@/lib/api";
import { toast } from "sonner";

export function HistoryTab({ entity, id }) {
  const { data } = useFetch(`/activity/${entity}/${id}`);
  return <Timeline items={(data || []).map((a) => ({ title: `${a.action.replace(/_/g, " ")} · ${a.label}`, details: a.details, meta: `${a.user_name} · ${fmtDateTime(a.at)}` }))} />;
}

function LinkCandidate({ open, onOpenChange, req, onDone }) {
  const { data } = useFetch("/candidates", {}, open);
  const linked = new Set((req.applications || []).filter((a) => !a.closed).map((a) => a.candidate_id));
  const options = (data || []).filter((c) => !linked.has(c.id)).map((c) => ({ value: c.id, label: `${c.name} · ${c.email || c.phone || c.code}` }));
  return (
    <FormDialog open={open} onOpenChange={onOpenChange} title="Link existing candidate" description={`${req.code} · ${req.title}`} testid="link-form" submitLabel="Link"
      fields={[{ name: "candidate_id", label: "Candidate", type: "select", options, required: true }]}
      onSubmit={async (v) => { try { await api.post("/applications", { candidate_id: v.candidate_id, requisition_id: req.id }); toast.success("Candidate linked"); onOpenChange(false); onDone(); } catch (e) { toast.error(errMsg(e)); } }} />
  );
}

export default function RequisitionDetail() {
  const { id } = useParams();
  const { can, meta } = useAuth();
  const { data: r, reload } = useFetch(`/requisitions/${id}`);
  const [dlg, setDlg] = useState(null);
  if (!r) return <p className="text-sm text-[#9AA2AE]">Loading…</p>;
  const apps = r.applications || [];
  const cols = [
    { key: "candidate_name", label: "Candidate", render: (a) => <Link to={`/candidates/${a.candidate_id}`} className="font-medium text-ink hover:underline">{a.candidate_name}</Link> },
    { key: "candidate_email", label: "Email" },
    { key: "current_company", label: "Company" },
    { key: "total_exp", label: "Exp" },
    { key: "expected_ctc", label: "Exp. CTC", render: (a) => lakhs(a.expected_ctc) },
    { key: "source", label: "Source" },
    { key: "status", label: "Stage", render: (a) => <StatusBadge status={a.status} /> },
    { key: "days_in_stage", label: "Days in stage", render: (a) => <span className={a.stuck ? "font-semibold text-amber-700" : ""}>{a.days_in_stage}</span> },
    { key: "actions", label: "", sortable: false, render: (a) => <AppActions app={a} onDone={reload} /> },
  ];
  return (
    <div>
      <PageHeader eyebrow={r.code} title={r.title} description={[r.department, r.location, r.employment_type].filter(Boolean).join(" · ")}
        actions={<>
          <StatusBadge status={r.status} className="text-xs" testid="req-status" />
          {can("cand.manage") && r.status === "Open" && <Button variant="outline" onClick={() => setDlg("link")} data-testid="req-link-candidate"><UserPlus className="mr-2 h-4 w-4" />Link candidate</Button>}
          {can("cand.manage") && r.status === "Open" && <Button variant="outline" onClick={() => setDlg("new")} data-testid="req-add-candidate">New candidate</Button>}
          {can("req.manage") && <Button onClick={() => setDlg("edit")} data-testid="req-edit-btn"><Pencil className="mr-2 h-4 w-4" />Edit</Button>}
        </>} />
      <div className="mb-6 grid gap-3 sm:grid-cols-4">
        <Section><p className="eyebrow">Positions filled</p><p className="mt-1 text-2xl font-extrabold" data-testid="req-filled">{r.filled_positions || 0} / {r.positions}</p><Progress value={r.positions ? (r.filled_positions / r.positions) * 100 : 0} className="mt-2 h-1.5" /></Section>
        <Section><p className="eyebrow">Open positions</p><p className="mt-1 text-2xl font-extrabold">{r.open_positions}</p></Section>
        <Section><p className="eyebrow">Candidates / active</p><p className="mt-1 text-2xl font-extrabold">{r.candidates_count} / {r.active_count}</p></Section>
        <Section><p className="eyebrow">Recruitment age</p><p className="mt-1 text-2xl font-extrabold">{r.age_days ?? "—"}{r.age_days != null && " d"}</p><p className="text-[11px] text-[#9AA2AE]">From {fmtDate(r.effective_start)}</p></Section>
      </div>
      <Tabs defaultValue="pipeline">
        <TabsList><TabsTrigger value="pipeline" data-testid="tab-pipeline">Pipeline</TabsTrigger><TabsTrigger value="details" data-testid="tab-details">Details</TabsTrigger><TabsTrigger value="history" data-testid="tab-history">History</TabsTrigger></TabsList>
        <TabsContent value="pipeline" className="space-y-4">
          <div className="flex flex-wrap gap-2">{[...meta.pipeline, ...meta.terminal].filter((s) => r.by_status[s]).map((s) => <span key={s} className="rounded-full border border-line bg-white px-3 py-1 text-xs">{s} <b>{r.by_status[s]}</b></span>)}</div>
          <DataTable testid="req-apps-table" columns={cols} data={apps} emptyTitle="No candidates linked yet" />
        </TabsContent>
        <TabsContent value="details">
          <Section><div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            <Info label="Hiring manager">{r.hiring_manager}</Info><Info label="Recruiter">{r.recruiter}</Info><Info label="Priority">{r.priority}</Info><Info label="Experience">{r.experience}</Info>
            <Info label="CTC range">{lakhs(r.min_ctc)} – {lakhs(r.max_ctc)}</Info><Info label="CRF raised">{r.crf_date ? fmtDate(r.crf_date) : <span className="text-amber-700">Missing — Age per Hire unavailable</span>}</Info><Info label="Current hiring age">{r.current_hiring_age != null ? `${r.current_hiring_age} days` : null}</Info><Info label="Recruitment initiated">{fmtDate(r.initiation_date)}</Info><Info label="Effective start">{fmtDate(r.effective_start)}</Info>
            <Info label="Skills">{r.skills?.join(", ")}</Info><Info label="Qualifications">{r.qualifications}</Info><Info label="Created by">{r.created_by_name} · {fmtDate(r.created_at)}</Info><Info label="Updated">{fmtDateTime(r.updated_at)}</Info>
            <div className="sm:col-span-2"><Info label="Remarks">{r.remarks}</Info></div><div className="sm:col-span-2"><Info label="Closure reason">{r.closure_reason}</Info></div>
          </div></Section>
        </TabsContent>
        <TabsContent value="history"><Section><HistoryTab entity="requisition" id={id} /></Section></TabsContent>
      </Tabs>
      <ReqForm open={dlg === "edit"} onOpenChange={(o) => !o && setDlg(null)} initial={r} onSaved={reload} />
      <LinkCandidate open={dlg === "link"} onOpenChange={(o) => !o && setDlg(null)} req={r} onDone={reload} />
      <CandidateDialog open={dlg === "new"} onOpenChange={(o) => !o && setDlg(null)} initial={{ requisition_id: r.id }} onSaved={reload}
        extraFields={[{ name: "requisition_id", label: "Requisition", type: "select", options: [{ value: r.id, label: `${r.code} ${r.title}` }] }]} />
    </div>
  );
}
