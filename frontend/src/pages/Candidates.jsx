import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Download, Plus, SlidersHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useAuth } from "@/context/AuthContext";
import { useFetch } from "@/lib/useFetch";
import { useUrlDefaults } from "@/lib/urlFilters";
import { PageHeader } from "@/components/common/Page";
import { DataTable } from "@/components/common/DataTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { SelectField } from "@/components/common/FormDialog";
import { CandidateDialog } from "@/components/forms";
import { download, lakhs, fmtDate } from "@/lib/api";

export default function Candidates() {
  const { can, list, meta } = useAuth();
  const nav = useNavigate();
  const [f, setF] = useState(useUrlDefaults({}, ["source_id", "status", "recruiter_id", "partner_id"]));
  const [open, setOpen] = useState(false);
  const { data, loading, reload } = useFetch("/candidates", f);
  const m = (t) => list(t).map((x) => ({ value: x.id, label: x.name }));
  const range = [["min_exp", "Min exp (yrs)"], ["max_exp", "Max exp (yrs)"], ["min_ctc", "Min current CTC"], ["max_ctc", "Max current CTC"], ["min_ectc", "Min expected CTC"], ["max_ectc", "Max expected CTC"], ["max_notice", "Max notice (days)"]];
  const cols = [
    { key: "code", label: "ID", render: (c) => <span className="font-mono text-xs">{c.code}</span> },
    { key: "name", label: "Name", render: (c) => <span className="font-medium text-ink">{c.name}</span> },
    { key: "email", label: "Email" },
    { key: "phone", label: "Mobile" },
    { key: "current_company", label: "Company" },
    { key: "current_designation", label: "Designation", hidden: true },
    { key: "total_exp", label: "Exp (yrs)" },
    { key: "current_ctc", label: "Current CTC", render: (c) => lakhs(c.current_ctc) },
    { key: "expected_ctc", label: "Expected CTC", render: (c) => lakhs(c.expected_ctc) },
    { key: "notice_period", label: "Notice" },
    { key: "roles", label: "Role(s)" },
    { key: "source", label: "Source" },
    { key: "partner", label: "Partner", hidden: true },
    { key: "recruiter", label: "Recruiter" },
    { key: "latest_status", label: "Latest stage", render: (c) => <StatusBadge status={c.latest_status} /> },
    { key: "created_at", label: "Added", render: (c) => fmtDate(c.created_at), hidden: true },
  ];
  return (
    <div>
      <PageHeader eyebrow="Recruitment" title="Candidates" description="Centralised candidate master. Stages are tracked per application, not per candidate."
        actions={<>
          {can("reports.export") && <Button variant="outline" onClick={() => download("/reports/candidates", f)} data-testid="cand-export-btn"><Download className="mr-2 h-4 w-4" />Export</Button>}
          {can("cand.manage") && <Button onClick={() => setOpen(true)} data-testid="cand-new-btn"><Plus className="mr-2 h-4 w-4" />Add candidate</Button>}
        </>} />
      <DataTable testid="cand-table" columns={cols} data={data} loading={loading} onRowClick={(c) => nav(`/candidates/${c.id}`)} searchPlaceholder="Name, email, phone, company, role…"
        toolbar={<>
          <SelectField value={f.status} onChange={(v) => setF({ ...f, status: v })} options={[...meta.pipeline, ...meta.terminal].map((s) => ({ value: s, label: s }))} placeholder="Any stage" testid="cand-filter-status" className="w-40" />
          <SelectField value={f.source_id} onChange={(v) => setF({ ...f, source_id: v })} options={m("source")} placeholder="All sources" testid="cand-filter-source" className="w-36" />
          <SelectField value={f.recruiter_id} onChange={(v) => setF({ ...f, recruiter_id: v })} options={m("recruiter")} placeholder="All recruiters" testid="cand-filter-recruiter" className="w-36" />
          <SelectField value={f.partner_id} onChange={(v) => setF({ ...f, partner_id: v })} options={m("partner")} placeholder="All partners" testid="cand-filter-partner" className="w-36" />
          <Popover>
            <PopoverTrigger asChild><Button variant="outline" size="sm" className="h-9" data-testid="cand-more-filters"><SlidersHorizontal className="mr-1.5 h-4 w-4" />Experience, CTC & notice</Button></PopoverTrigger>
            <PopoverContent className="grid w-72 grid-cols-2 gap-2">
              {range.map(([k, l]) => <div key={k}><p className="mb-1 text-[11px] text-subtle">{l}</p><Input type="number" className="h-8" value={f[k] || ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} data-testid={`cand-filter-${k}`} /></div>)}
              <Button variant="ghost" size="sm" className="col-span-2" onClick={() => setF({})}>Clear all filters</Button>
            </PopoverContent>
          </Popover>
        </>} />
      <CandidateDialog open={open} onOpenChange={setOpen} onSaved={(c) => { reload(); nav(`/candidates/${c.id}`); }} />
    </div>
  );
}
