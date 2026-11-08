import { useRef, useState } from "react";
import { Download, FileText, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useAuth } from "@/context/AuthContext";
import { useFetch } from "@/lib/useFetch";
import { useUrlDefaults } from "@/lib/urlFilters";
import { Info, PageHeader, Timeline } from "@/components/common/Page";
import { DataTable } from "@/components/common/DataTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { SelectField } from "@/components/common/FormDialog";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { OfferDialog } from "@/components/forms";
import { api, download, errMsg, fmtDate, fmtDateTime, lakhs } from "@/lib/api";
import { toast } from "sonner";

const BTN = {
  submit: { label: "Submit for approval", from: ["Draft"], perm: "offer.manage" },
  approve: { label: "Approve", from: ["Approval Pending"], perm: "offer.approve" },
  reject: { label: "Reject approval", from: ["Approval Pending"], perm: "offer.approve", reason: true },
  release: { label: "Release offer", from: ["Approved"], perm: "offer.manage", date: "Release date" },
  accept: { label: "Record acceptance", from: ["Released"], perm: "offer.manage", date: "Accepted date" },
  decline: { label: "Record decline", from: ["Released", "Approved"], perm: "offer.manage", reason: true, date: "Declined date" },
  revoke: { label: "Revoke", from: ["Approved", "Released", "Accepted"], perm: "offer.manage", reason: true },
};

function OfferDetail({ offer, onClose, onChanged }) {
  const { can } = useAuth();
  const [act, setAct] = useState(null);
  const [edit, setEdit] = useState(false);
  const ref = useRef();
  if (!offer) return null;
  const run = async (action, extra = {}) => {
    try { await api.post(`/offers/${offer.id}/action`, { action, ...extra }); toast.success("Offer updated"); onChanged(); } catch (e) { toast.error(errMsg(e)); throw e; }
  };
  const upload = async (file) => {
    const fd = new FormData(); fd.append("entity", "offer"); fd.append("entity_id", offer.id); fd.append("file", file);
    try { await api.post("/files", fd); toast.success("Offer document uploaded"); onChanged(); } catch (e) { toast.error(errMsg(e)); }
  };
  const cfg = act && BTN[act];
  return (
    <Sheet open={!!offer} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl" data-testid="offer-detail">
        <SheetHeader><p className="font-mono text-[11px] text-zinc-400">{offer.code}</p><SheetTitle>{offer.candidate_name}</SheetTitle><p className="text-sm text-zinc-500">{offer.designation} · {offer.requisition_title}</p></SheetHeader>
        <div className="my-4 flex gap-2"><StatusBadge status={offer.status} testid="offer-status" /><StatusBadge status={offer.approval_status} /></div>
        <div className="grid grid-cols-2 gap-4">
          <Info label="Offered CTC">{lakhs(offer.ctc)}</Info><Info label="Breakdown">Fixed {lakhs(offer.fixed)} · Var {lakhs(offer.variable)} · Other {lakhs(offer.other)}</Info>
          <Info label="Released">{fmtDate(offer.release_date)}</Info><Info label="Valid until">{fmtDate(offer.validity_date)}</Info>
          <Info label="Accepted">{fmtDate(offer.accepted_date)}</Info><Info label="Declined">{fmtDate(offer.declined_date)}</Info>
          {offer.decline_reason && <div className="col-span-2"><Info label="Decline reason">{offer.decline_reason}</Info></div>}
          {offer.approved_by && <Info label="Approved by">{offer.approved_by}</Info>}
          <Info label="Offer document">{offer.document ? <button className="underline" onClick={() => download(`/files/${offer.document.file_id}`)} data-testid="offer-doc-download">{offer.document.name}</button> : null}</Info>
        </div>
        <div className="my-5 flex flex-wrap gap-2">
          {Object.entries(BTN).filter(([, b]) => b.from.includes(offer.status) && can(b.perm)).map(([k, b]) => (
            <Button key={k} size="sm" variant={["approve", "release", "accept", "submit"].includes(k) ? "default" : "outline"} data-testid={`offer-action-${k}`}
              onClick={() => (b.reason || b.date ? setAct(k) : run(k))}>{b.label}</Button>))}
          {can("offer.manage") && ["Draft", "Approval Pending"].includes(offer.status) && <Button size="sm" variant="outline" onClick={() => setEdit(true)} data-testid="offer-edit-btn">Edit</Button>}
          {can("offer.manage") && <><input ref={ref} type="file" hidden accept=".pdf,.docx" onChange={(e) => e.target.files[0] && upload(e.target.files[0])} />
            <Button size="sm" variant="outline" onClick={() => ref.current.click()} data-testid="offer-upload-btn"><Upload className="mr-1.5 h-3.5 w-3.5" />Upload document</Button></>}
        </div>
        <h4 className="eyebrow mb-2">Offer history</h4>
        <Timeline items={[...(offer.history || [])].reverse().map((h) => ({ title: h.action, details: h.details, meta: `${h.by} · ${fmtDateTime(h.at)}` }))} />
        {cfg && <ConfirmDialog open={!!act} onOpenChange={(o) => !o && setAct(null)} title={cfg.label} reason={cfg.reason} dateLabel={cfg.date} testid="offer-confirm"
          destructive={["reject", "decline", "revoke"].includes(act)} confirmLabel={cfg.label} onConfirm={({ reason, date }) => run(act, { reason, date })} />}
        <OfferDialog open={edit} onOpenChange={setEdit} offer={offer} app={{ candidate_name: offer.candidate_name, requisition_title: offer.requisition_title }} onDone={onChanged} />
      </SheetContent>
    </Sheet>
  );
}

export default function Offers() {
  const { meta, can } = useAuth();
  const [f, setF] = useState(useUrlDefaults({}, ["status"]));
  const [sel, setSel] = useState(null);
  const { data, loading, reload } = useFetch("/offers", f);
  const current = sel && (data || []).find((o) => o.id === sel);
  const today = new Date().toISOString().slice(0, 10);
  const cols = [
    { key: "code", label: "Offer ID", render: (o) => <span className="font-mono text-xs">{o.code}</span> },
    { key: "candidate_name", label: "Candidate", render: (o) => <span className="font-medium text-zinc-900">{o.candidate_name}</span> },
    { key: "requisition_title", label: "Role" },
    { key: "designation", label: "Designation" },
    { key: "ctc", label: "CTC", render: (o) => lakhs(o.ctc) },
    { key: "status", label: "Status", render: (o) => <StatusBadge status={o.status} /> },
    { key: "approval_status", label: "Approval", render: (o) => <StatusBadge status={o.approval_status} /> },
    { key: "release_date", label: "Released", render: (o) => fmtDate(o.release_date) },
    { key: "validity_date", label: "Valid until", render: (o) => <span className={o.status === "Released" && o.validity_date <= today ? "font-semibold text-rose-700" : ""}>{fmtDate(o.validity_date)}</span> },
    { key: "document", label: "Doc", sortable: false, render: (o) => (o.document ? <FileText className="h-4 w-4 text-zinc-500" /> : "—") },
  ];
  const pending = (data || []).filter((o) => o.status === "Approval Pending").length;
  return (
    <div>
      <PageHeader eyebrow="Selection & offers" title="Offers" description="Draft → approval → release → acceptance. Create offers from a selected candidate's application."
        actions={can("reports.export") && <Button variant="outline" onClick={() => download("/reports/offers", f)} data-testid="offer-export-btn"><Download className="mr-2 h-4 w-4" />Export</Button>} />
      {pending > 0 && <p className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900" data-testid="offer-pending-alert">{pending} offer(s) awaiting approval</p>}
      <DataTable testid="offer-table" columns={cols} data={data} loading={loading} onRowClick={(o) => setSel(o.id)} emptyHint="Offers appear here once created for a selected candidate."
        toolbar={<SelectField value={f.status} onChange={(v) => setF({ ...f, status: v })} options={meta.offer_statuses.map((s) => ({ value: s, label: s }))} placeholder="All statuses" testid="offer-filter-status" className="w-44" />} />
      <OfferDetail offer={current} onClose={() => setSel(null)} onChanged={reload} />
    </div>
  );
}
