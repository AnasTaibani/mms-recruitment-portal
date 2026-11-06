import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { useAuth } from "@/context/AuthContext";
import { useFetch } from "@/lib/useFetch";
import { PageHeader } from "@/components/common/Page";
import { DataTable } from "@/components/common/DataTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { FormDialog, SelectField } from "@/components/common/FormDialog";
import { reqFields, toSkills } from "@/components/forms";
import { api, download, errMsg, fmtDate, lakhs } from "@/lib/api";
import { toast } from "sonner";

export function ReqForm({ open, onOpenChange, initial, onSaved }) {
  const { meta } = useAuth();
  return (
    <FormDialog open={open} onOpenChange={onOpenChange} wide title={initial?.id ? `Edit ${initial.code}` : "New requisition"} testid="req-form"
      fields={reqFields(meta)} initial={initial ? { ...initial, skills: (initial.skills || []).join(", "), department_name: initial.department || "", hiring_manager_name: initial.hiring_manager || "", location_name: initial.location || "" } : null}
      onSubmit={async (v) => {
        try {
          const body = { ...v, skills: toSkills(v.skills) };
          const r = initial?.id ? await api.put(`/requisitions/${initial.id}`, body) : await api.post("/requisitions", body);
          toast.success(initial?.id ? "Requisition updated" : `Requisition ${r.data.code} created`);
          onOpenChange(false); onSaved?.(r.data);
        } catch (e) { toast.error(errMsg(e)); }
      }} />
  );
}

export default function Requisitions() {
  const { can, list, meta } = useAuth();
  const nav = useNavigate();
  const [f, setF] = useState({});
  const [open, setOpen] = useState(false);
  const { data, loading, reload } = useFetch("/requisitions", f);
  const flt = (k, opts, ph) => <SelectField value={f[k]} onChange={(v) => setF({ ...f, [k]: v })} options={opts} placeholder={ph} testid={`req-filter-${k}`} className="w-40" />;
  const cols = [
    { key: "code", label: "Req ID", render: (r) => <span className="font-mono text-xs">{r.code}</span> },
    { key: "title", label: "Job Title", render: (r) => <span className="font-medium text-zinc-900">{r.title}</span> },
    { key: "department", label: "Department" },
    { key: "hiring_manager", label: "Hiring Manager" },
    { key: "recruiter", label: "Recruiter" },
    { key: "positions", label: "Filled / Total", value: (r) => r.filled_positions, render: (r) => (
      <div className="w-28"><p className="text-xs">{r.filled_positions || 0} / {r.positions}</p><Progress value={r.positions ? ((r.filled_positions || 0) / r.positions) * 100 : 0} className="mt-1 h-1.5" /></div>) },
    { key: "candidates_count", label: "Candidates" },
    { key: "active_count", label: "Active" },
    { key: "max_ctc", label: "CTC Range", render: (r) => `${r.min_ctc ?? "—"} – ${r.max_ctc ?? "—"} L`, hidden: true },
    { key: "priority", label: "Priority", render: (r) => <StatusBadge status={r.priority} /> },
    { key: "status", label: "Status", render: (r) => <StatusBadge status={r.status} /> },
    { key: "crf_date", label: "CRF Raised", render: (r) => r.crf_date ? fmtDate(r.crf_date) : <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[11px] font-semibold text-amber-800" title={r.aph_flag} data-testid="req-crf-missing">Missing — add CRF</span> },
    { key: "current_hiring_age", label: "Hiring age (d)", value: (r) => r.current_hiring_age },
    { key: "age_days", label: "Age (days)", hidden: true },
    { key: "location", label: "Location", hidden: true },
    { key: "max", label: "Max CTC", value: (r) => r.max_ctc, render: (r) => lakhs(r.max_ctc), hidden: true },
  ];
  return (
    <div>
      <PageHeader eyebrow="Recruitment" title="Requisitions" description="Open roles, vacancies and the candidate pipeline against each."
        actions={<>
          {can("reports.export") && <Button variant="outline" onClick={() => download("/reports/requisitions", f)} data-testid="req-export-btn"><Download className="mr-2 h-4 w-4" />Export</Button>}
          {can("req.manage") && <Button onClick={() => setOpen(true)} data-testid="req-new-btn"><Plus className="mr-2 h-4 w-4" />New requisition</Button>}
        </>} />
      <DataTable testid="req-table" columns={cols} data={data} loading={loading} onRowClick={(r) => nav(`/requisitions/${r.id}`)}
        emptyHint="Create a requisition or import the Open Roles Master sheet."
        toolbar={<>
          {flt("status", meta.req_statuses.map((s) => ({ value: s, label: s })), "All statuses")}
          {flt("department_id", list("department").map((m) => ({ value: m.id, label: m.name })), "All departments")}
          {flt("recruiter_id", list("recruiter").map((m) => ({ value: m.id, label: m.name })), "All recruiters")}
          <input type="date" className="h-9 rounded-md border px-2 text-xs" value={f.date_from || ""} onChange={(e) => setF({ ...f, date_from: e.target.value })} data-testid="req-filter-from" title="Created from" />
          <input type="date" className="h-9 rounded-md border px-2 text-xs" value={f.date_to || ""} onChange={(e) => setF({ ...f, date_to: e.target.value })} data-testid="req-filter-to" title="Created to" />
        </>} />
      <ReqForm open={open} onOpenChange={setOpen} onSaved={(r) => { reload(); nav(`/requisitions/${r.id}`); }} />
    </div>
  );
}
