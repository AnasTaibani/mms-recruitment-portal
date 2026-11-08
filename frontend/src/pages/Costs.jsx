import { useState } from "react";
import { Download, Pencil, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { useFetch } from "@/lib/useFetch";
import { Kpi, PageHeader, Section } from "@/components/common/Page";
import { DataTable } from "@/components/common/DataTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { FormDialog, SelectField } from "@/components/common/FormDialog";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { api, download, errMsg, fmtDate, lakhs } from "@/lib/api";
import { toast } from "sonner";

const LAKH_MSG = "Enter in ₹ lakhs — e.g. 35 for ₹35 lakh (not 3500000)";
const rupees = (l) => (l === null || l === undefined || l === "" || Number.isNaN(Number(l)) ? "" : `= ₹${Math.round(Number(l) * 100000).toLocaleString("en-IN")}`);
const feeOf = (v) => (v.ctc !== "" && v.ctc != null && v.fee_percent !== "" && v.fee_percent != null ? Math.round(Number(v.ctc) * Number(v.fee_percent) * 100) / 10000 : undefined);

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
    { name: "candidate_id", label: "Related Candidate", type: "select", options: (cands || []).map((c) => ({ value: c.id, label: `${c.name} (${c.code})` })) },
    { name: "requisition_id", label: "Related Requisition", type: "select", options: (reqs || []).map((r) => ({ value: r.id, label: `${r.code} ${r.title}` })) },
    { name: "recruiter_id", label: "Recruiter", master: "recruiter" },
    { name: "partner_name", label: "Recruitment Partner", suggest: "partner", placeholder: "Type the partner / consultancy name" },
    { name: "ctc", label: "Candidate CTC (₹ L)", type: "number", max: 1000, maxMessage: LAKH_MSG, placeholder: "e.g. 35",
      help: (v) => rupees(v.ctc) || "Only used here to work out a %-based fee. The hire's CTC for Cost per Hire is confirmed on the candidate before joining." },
    { name: "fee_percent", label: "Fee %", type: "number", max: 100, maxMessage: "Enter a percentage between 0 and 100", placeholder: "e.g. 8.33",
      help: "Partner fee as % of CTC — e.g. 8.33 for M2S, 7 for others" },
    { name: "amount", label: "Fee Amount (₹ L) — leave blank if not yet known", type: "number", max: 1000, maxMessage: LAKH_MSG,
      derive: { from: ["ctc", "fee_percent"], fn: feeOf },
      help: (v) => [rupees(v.amount), feeOf(v) !== undefined && "auto: CTC × Fee %"].filter(Boolean).join(" · ") || "Filled in automatically from CTC × Fee %, or type a fixed amount" },
    { name: "invoice_no", label: "Invoice Number" },
    { name: "invoice_date", label: "Invoice Date (if received)", type: "date" },
    { name: "payment_status", label: "Payment Status", type: "select", options: meta.payment_statuses.map((s) => ({ value: s, label: s })), default: "Pending" },
    { name: "payment_date", label: "Payment Date", type: "date" },
    { name: "remarks", label: "Remarks", type: "textarea" },
  ];
  const refresh = () => { reload(); reloadAn(); };
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
    { key: "ctc", label: "CTC", render: (c) => lakhs(c.ctc) },
    { key: "fee_percent", label: "Fee %", render: (c) => (c.fee_percent == null ? "—" : `${c.fee_percent}%`) },
    { key: "amount", label: "Fee amount", render: (c) => <b>{lakhs(c.amount)}</b> },
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
      <PageHeader eyebrow="Finance" title="Recruitment Costs" description="Cost per Hire = Candidate annual CTC + Consulting fees + Recruiter fees, confirmed for every candidate before joining. Average = sum of Cost per Hire ÷ joined candidates with confirmed cost. Amounts in ₹ lakhs."
        actions={<>
          {can("reports.export") && <Button variant="outline" onClick={() => download("/reports/costs", f)} data-testid="cost-export-btn"><Download className="mr-2 h-4 w-4" />Export</Button>}
          {can("cost.manage") && <Button onClick={() => setEdit({})} data-testid="cost-new-btn"><Plus className="mr-2 h-4 w-4" />Add cost</Button>}
        </>} />
      <div className="mb-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Kpi label="Average cost per hire" value={an?.cost ? (an.cost.cost_per_hire === null ? "N/A" : lakhs(an.cost.cost_per_hire)) : "—"} hint="Sum of Cost per Hire ÷ hires with confirmed cost" testid="cost-per-hire" />
        <Kpi label="Total hiring cost" value={an?.cost ? lakhs(an.cost.total) : "—"} hint="CTC + consulting + recruiter fees" testid="cost-total" />
        <Kpi label="Candidate CTC" value={an?.cost ? lakhs(an.cost.ctc_total) : "—"} hint="Annual CTC of joined hires" testid="cost-ctc-total" />
        <Kpi label="Consulting + recruiter fees" value={an?.cost ? lakhs(an.cost.fees) : "—"} hint={an?.cost ? `Consulting ${lakhs(an.cost.consulting_total)} · recruiter ${lakhs(an.cost.recruiter_total)}` : ""} testid="cost-fees" />
        <Kpi label="Hires counted" value={an?.cost ? `${an.cost.hires} / ${an.cost.joined}` : "—"} hint="Joined with confirmed cost / all joined" testid="cost-hires" />
      </div>
      {an?.cost?.unconfirmed > 0 && <p className="mb-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800" data-testid="cost-unconfirmed">{an.cost.unconfirmed} joined candidate(s) have no confirmed cost (usually records from before this rule) and are not counted as completed hires in the average. Confirm their cost from the candidate's application menu.</p>}
      <Section title="Cost per hire by candidate" className="mb-4" testid="cost-per-hire-section"
        actions={can("reports.export") && <Button size="sm" variant="outline" onClick={() => download("/reports/cost-per-hire", f)} data-testid="cost-per-hire-export"><Download className="mr-2 h-4 w-4" />Export</Button>}>
        <DataTable testid="cost-per-hire-table" data={an?.cost?.hire_costs || []} loading={!an} pageSize={8} emptyTitle="No joined candidates in this period"
          columns={[{ key: "candidate", label: "Candidate" }, { key: "role", label: "Role" }, { key: "joined_on", label: "Joined", render: (r) => fmtDate(r.joined_on) },
            { key: "ctc", label: "Annual CTC", render: (r) => lakhs(r.ctc) }, { key: "consulting_fee", label: "Consulting", render: (r) => lakhs(r.consulting_fee) },
            { key: "recruiter_fee", label: "Recruiter", render: (r) => lakhs(r.recruiter_fee) },
            { key: "total", label: "Cost per hire", render: (r) => (r.total == null ? <span className="text-xs font-semibold text-amber-700">Not confirmed</span> : <b>{lakhs(r.total)}</b>) },
            { key: "confirmed_by", label: "Confirmed by", hidden: true }]} />
      </Section>
      <p className="eyebrow mb-2">Invoices &amp; fee entries</p>
      <DataTable testid="cost-table" columns={cols} data={data} loading={loading}
        toolbar={<>
          {sel("category_id", m("cost_category"), "All categories")}
          {sel("recruiter_id", m("recruiter"), "All recruiters")}
          {sel("partner_id", m("partner"), "All partners")}
          {sel("department_id", m("department"), "All departments")}
          <input type="date" className="h-9 rounded-md border px-2 text-xs" value={f.date_from || ""} onChange={(e) => setF({ ...f, date_from: e.target.value })} data-testid="cost-filter-from" />
          <input type="date" className="h-9 rounded-md border px-2 text-xs" value={f.date_to || ""} onChange={(e) => setF({ ...f, date_to: e.target.value })} data-testid="cost-filter-to" />
        </>} />
      <FormDialog open={!!edit} onOpenChange={(o) => !o && setEdit(null)} title={edit?.id ? `Edit ${edit.code}` : "Add recruitment cost"} wide fields={fields} initial={edit ? { ...edit, partner_name: edit.partner || "" } : edit} testid="cost-form"
        onSubmit={async (v) => { try { edit.id ? await api.put(`/costs/${edit.id}`, v) : await api.post("/costs", v); toast.success("Cost saved"); setEdit(null); refresh(); } catch (e) { toast.error(errMsg(e)); } }} />
      <ConfirmDialog open={!!del} onOpenChange={(o) => !o && setDel(null)} title={`Delete ${del?.code}?`} description="This removes the cost record. The deletion is recorded in the activity log." destructive confirmLabel="Delete" testid="cost-delete"
        onConfirm={async () => { try { await api.delete(`/costs/${del.id}`); toast.success("Deleted"); refresh(); } catch (e) { toast.error(errMsg(e)); throw e; } }} />
    </div>
  );
}
