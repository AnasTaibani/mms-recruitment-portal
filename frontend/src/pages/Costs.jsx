import { useState } from "react";
import { Download, Pencil, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { useFetch } from "@/lib/useFetch";
import { Kpi, PageHeader } from "@/components/common/Page";
import { DataTable } from "@/components/common/DataTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { FormDialog, SelectField } from "@/components/common/FormDialog";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { api, download, errMsg, fmtDate, lakhs } from "@/lib/api";
import { toast } from "sonner";

export default function Costs() {
  const { can, list, meta } = useAuth();
  const [f, setF] = useState({});
  const [edit, setEdit] = useState(null);
  const [del, setDel] = useState(null);
  const { data, loading, reload } = useFetch("/costs", f);
  const { data: an, reload: reloadAn } = useFetch("/analytics", f);
  const { data: reqs } = useFetch("/requisitions");
  const { data: cands } = useFetch("/candidates");
  const m = (t) => list(t).map((x) => ({ value: x.id, label: x.name }));
  const fields = [
    { name: "category_id", label: "Cost Category", master: "cost_category", required: true },
    { name: "amount", label: "Amount (₹ L)", type: "number", required: true },
    { name: "recruiter_id", label: "Recruiter", master: "recruiter" },
    { name: "partner_id", label: "Recruitment Partner", master: "partner" },
    { name: "requisition_id", label: "Related Requisition", type: "select", options: (reqs || []).map((r) => ({ value: r.id, label: `${r.code} ${r.title}` })) },
    { name: "candidate_id", label: "Related Candidate", type: "select", options: (cands || []).map((c) => ({ value: c.id, label: `${c.name} (${c.code})` })) },
    { name: "invoice_no", label: "Invoice Number" },
    { name: "invoice_date", label: "Invoice Date", type: "date", required: true },
    { name: "payment_status", label: "Payment Status", type: "select", options: meta.payment_statuses.map((s) => ({ value: s, label: s })), default: "Pending" },
    { name: "payment_date", label: "Payment Date", type: "date" },
    { name: "remarks", label: "Remarks", type: "textarea" },
  ];
  const refresh = () => { reload(); reloadAn(); };
  const total = (data || []).reduce((s, c) => s + (c.amount || 0), 0);
  const cols = [
    { key: "code", label: "Cost ID", render: (c) => <span className="font-mono text-xs">{c.code}</span> },
    { key: "category", label: "Category" },
    { key: "recruiter", label: "Recruiter" },
    { key: "partner", label: "Partner" },
    { key: "requisition_title", label: "Requisition" },
    { key: "department", label: "Department", hidden: true },
    { key: "candidate_name", label: "Candidate" },
    { key: "invoice_no", label: "Invoice #" },
    { key: "invoice_date", label: "Invoice date", render: (c) => fmtDate(c.invoice_date) },
    { key: "amount", label: "Amount", render: (c) => <b>{lakhs(c.amount)}</b> },
    { key: "payment_status", label: "Payment", render: (c) => <StatusBadge status={c.payment_status} /> },
    { key: "payment_date", label: "Paid on", render: (c) => fmtDate(c.payment_date), hidden: true },
    ...(can("cost.manage") ? [{ key: "actions", label: "", sortable: false, render: (c) => (
      <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
        <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => setEdit(c)} data-testid={`cost-edit-${c.code}`}><Pencil className="h-3.5 w-3.5" /></Button>
        <Button size="icon" variant="ghost" className="h-8 w-8 text-rose-600" onClick={() => setDel(c)} data-testid={`cost-delete-${c.code}`}><Trash2 className="h-3.5 w-3.5" /></Button>
      </div>) }] : []),
  ];
  const sel = (k, opts, ph) => <SelectField value={f[k]} onChange={(v) => setF({ ...f, [k]: v })} options={opts} placeholder={ph} testid={`cost-filter-${k}`} className="w-40" />;
  return (
    <div>
      <PageHeader eyebrow="Finance" title="Recruitment Costs" description="Cost per Hire = Total Recruitment Costs ÷ Total Candidates Joined (joined candidates only)."
        actions={<>
          {can("reports.export") && <Button variant="outline" onClick={() => download("/reports/costs", f)} data-testid="cost-export-btn"><Download className="mr-2 h-4 w-4" />Export</Button>}
          {can("cost.manage") && <Button onClick={() => setEdit({})} data-testid="cost-new-btn"><Plus className="mr-2 h-4 w-4" />Add cost</Button>}
        </>} />
      <div className="mb-5 grid gap-3 sm:grid-cols-4">
        <Kpi label="Total cost (filtered)" value={lakhs(total)} testid="cost-total" />
        <Kpi label="Paid" value={lakhs((data || []).filter((c) => c.payment_status === "Paid").reduce((s, c) => s + c.amount, 0))} />
        <Kpi label="Candidates joined" value={an?.cost?.hires ?? "—"} hint="Denominator (actual joiners)" />
        <Kpi label="Cost per hire" value={an?.cost ? (an.cost.cost_per_hire === null ? "N/A" : lakhs(an.cost.cost_per_hire)) : "—"} testid="cost-per-hire" />
      </div>
      <DataTable testid="cost-table" columns={cols} data={data} loading={loading}
        toolbar={<>
          {sel("category_id", m("cost_category"), "All categories")}
          {sel("recruiter_id", m("recruiter"), "All recruiters")}
          {sel("partner_id", m("partner"), "All partners")}
          {sel("department_id", m("department"), "All departments")}
          <input type="date" className="h-9 rounded-md border px-2 text-xs" value={f.date_from || ""} onChange={(e) => setF({ ...f, date_from: e.target.value })} data-testid="cost-filter-from" />
          <input type="date" className="h-9 rounded-md border px-2 text-xs" value={f.date_to || ""} onChange={(e) => setF({ ...f, date_to: e.target.value })} data-testid="cost-filter-to" />
        </>} />
      <FormDialog open={!!edit} onOpenChange={(o) => !o && setEdit(null)} title={edit?.id ? `Edit ${edit.code}` : "Add recruitment cost"} wide fields={fields} initial={edit} testid="cost-form"
        onSubmit={async (v) => { try { edit.id ? await api.put(`/costs/${edit.id}`, v) : await api.post("/costs", v); toast.success("Cost saved"); setEdit(null); refresh(); } catch (e) { toast.error(errMsg(e)); } }} />
      <ConfirmDialog open={!!del} onOpenChange={(o) => !o && setDel(null)} title={`Delete ${del?.code}?`} description="This removes the cost record. The deletion is recorded in the activity log." destructive confirmLabel="Delete" testid="cost-delete"
        onConfirm={async () => { try { await api.delete(`/costs/${del.id}`); toast.success("Deleted"); refresh(); } catch (e) { toast.error(errMsg(e)); throw e; } }} />
    </div>
  );
}
