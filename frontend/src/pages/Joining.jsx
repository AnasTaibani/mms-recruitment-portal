import { useEffect, useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useAuth } from "@/context/AuthContext";
import { useFetch } from "@/lib/useFetch";
import { PageHeader, Timeline } from "@/components/common/Page";
import { DataTable } from "@/components/common/DataTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { SelectField } from "@/components/common/FormDialog";
import { api, download, errMsg, fmtDate, fmtDateTime } from "@/lib/api";
import { toast } from "sonner";

function JoinSheet({ j, onClose, onChanged }) {
  const { meta, can } = useAuth();
  const [v, setV] = useState({});
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (j) setV({ tentative_date: j.tentative_date || "", confirmed_date: j.confirmed_date || "", actual_date: j.actual_date || "", status: j.status, checklist: j.checklist || [], remarks: j.remarks || "", reason: "" }); }, [j]);
  if (!j) return null;
  const locked = ["Joined", "Cancelled", "No Show"].includes(j.status);
  const edit = can("joining.manage") && !locked;
  const save = async () => {
    setBusy(true);
    try {
      const body = { ...v, status: v.status === j.status ? undefined : v.status };
      Object.keys(body).forEach((k) => body[k] === "" && (body[k] = null));
      await api.put(`/joinings/${j.id}`, body);
      toast.success("Joining record updated"); onChanged();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const d = (k, l) => <div className="space-y-1"><Label className="text-xs">{l}</Label><Input type="date" disabled={!edit} value={v[k] || ""} onChange={(e) => setV({ ...v, [k]: e.target.value })} data-testid={`join-${k}`} /></div>;
  const needReason = ["Joining Deferred", "No Show", "Cancelled"].includes(v.status) && v.status !== j.status;
  return (
    <Sheet open={!!j} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-lg" data-testid="joining-detail">
        <SheetHeader><p className="font-mono text-[11px] text-[#9AA2AE]">{j.code}</p><SheetTitle>{j.candidate_name}</SheetTitle><p className="text-sm text-subtle">{j.requisition_title} · Recruiter {j.recruiter || "—"}{j.partner && ` · ${j.partner}`}</p></SheetHeader>
        <div className="my-4"><StatusBadge status={j.status} testid="join-status" /></div>
        <div className="grid grid-cols-2 gap-3">
          {d("tentative_date", "Tentative joining date")}{d("confirmed_date", "Confirmed joining date")}{d("actual_date", "Actual date of joining")}
          <div className="space-y-1"><Label className="text-xs">Joining status</Label>
            {edit ? <SelectField value={v.status} onChange={(s) => setV({ ...v, status: s })} options={meta.joining_statuses.map((s) => ({ value: s, label: s }))} allowNone={false} testid="join-status-select" /> : <p className="text-sm">{j.status}</p>}</div>
        </div>
        {needReason && <div className="mt-3 space-y-1"><Label className="text-xs">Reason *</Label><Textarea rows={2} value={v.reason} onChange={(e) => setV({ ...v, reason: e.target.value })} data-testid="join-reason" /></div>}
        <h4 className="eyebrow mb-2 mt-5">Document checklist ({(v.checklist || []).filter((c) => c.received).length}/{(v.checklist || []).length} received)</h4>
        <div className="space-y-2">{(v.checklist || []).map((c, i) => (
          <label key={c.item} className="flex items-center gap-2 text-sm"><Checkbox disabled={!can("joining.manage")} checked={c.received} data-testid={`join-doc-${i}`}
            onCheckedChange={(x) => setV({ ...v, checklist: v.checklist.map((y, k) => (k === i ? { ...y, received: !!x } : y)) })} />{c.item}</label>))}
          {!v.checklist?.length && <p className="text-xs text-[#9AA2AE]">No checklist items. Configure them under Master Data → Joining Document Checklist.</p>}</div>
        <div className="mt-4 space-y-1"><Label className="text-xs">Onboarding remarks</Label><Textarea rows={3} disabled={!can("joining.manage")} value={v.remarks} onChange={(e) => setV({ ...v, remarks: e.target.value })} data-testid="join-remarks" /></div>
        {can("joining.manage") && <Button className="mt-4 w-full" onClick={save} disabled={busy} data-testid="join-save">{busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Save changes</Button>}
        <h4 className="eyebrow mb-2 mt-6">History</h4>
        <Timeline items={[...(j.history || [])].reverse().map((h) => ({ title: h.action, details: h.details, meta: `${h.by} · ${fmtDateTime(h.at)}` }))} />
      </SheetContent>
    </Sheet>
  );
}

export default function Joining() {
  const { meta, can } = useAuth();
  const [f, setF] = useState({});
  const [sel, setSel] = useState(null);
  const { data, loading, reload } = useFetch("/joinings", f);
  const cur = sel && (data || []).find((x) => x.id === sel);
  const cols = [
    { key: "code", label: "ID", render: (j) => <span className="font-mono text-xs">{j.code}</span> },
    { key: "candidate_name", label: "Candidate", render: (j) => <span className="font-medium text-ink">{j.candidate_name}</span> },
    { key: "requisition_title", label: "Role" },
    { key: "recruiter", label: "Recruiter" },
    { key: "partner", label: "Partner" },
    { key: "tentative_date", label: "Tentative", render: (j) => fmtDate(j.tentative_date) },
    { key: "confirmed_date", label: "Confirmed", render: (j) => fmtDate(j.confirmed_date) },
    { key: "actual_date", label: "Actual DOJ", render: (j) => fmtDate(j.actual_date) },
    { key: "docs", label: "Documents", value: (j) => (j.checklist || []).filter((c) => c.received).length, render: (j) => `${(j.checklist || []).filter((c) => c.received).length}/${(j.checklist || []).length}` },
    { key: "status", label: "Status", render: (j) => <StatusBadge status={j.status} /> },
  ];
  return (
    <div>
      <PageHeader eyebrow="Onboarding" title="Joining" description="Created automatically when an offer is accepted. Only candidates marked Joined count as hires."
        actions={can("reports.export") && <Button variant="outline" onClick={() => download("/reports/joinings", f)} data-testid="join-export-btn"><Download className="mr-2 h-4 w-4" />Export</Button>} />
      <DataTable testid="join-table" columns={cols} data={data} loading={loading} onRowClick={(j) => setSel(j.id)} emptyHint="Joining records appear once a candidate accepts an offer."
        toolbar={<SelectField value={f.status} onChange={(v) => setF({ ...f, status: v })} options={meta.joining_statuses.map((s) => ({ value: s, label: s }))} placeholder="All statuses" testid="join-filter-status" className="w-44" />} />
      <JoinSheet j={cur} onClose={() => setSel(null)} onChanged={reload} />
    </div>
  );
}
