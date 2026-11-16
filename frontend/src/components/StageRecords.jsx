import { useCallback, useEffect, useState } from "react";
import { Pencil } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { FormDialog } from "@/components/common/FormDialog";
import { useAuth } from "@/context/AuthContext";
import { api, errMsg, fmtDate, fmtDateTime, lakhs } from "@/lib/api";

const today = () => new Date().toISOString().slice(0, 10);

/* Edit a saved Screening / Shortlisting / Selection record: date, owner or decision maker, remarks (and compensation).
   The decision itself can't be changed here, and every edit needs a reason (kept in the record's edit history). */
export function EditRecordDialog({ open, onOpenChange, record, onSaved }) {
  const { list } = useAuth();
  if (!record) return null;
  const sel = record.kind === "selection";
  const recruiters = list("recruiter").slice().sort((a, b) => a.name.localeCompare(b.name));
  const fields = sel ? [
    { name: "selection_date", label: "Selection date", type: "date", required: true, max: today() },
    { name: "decision_maker", label: "Decision maker", required: true },
    ...(record.decision === "Selected" ? [{ name: "compensation", label: "Selected compensation (₹ L)", type: "number", required: true }] : []),
    { name: "remarks", label: record.decision === "Selected" ? "Remarks" : "Remarks (required for reject / hold)", type: "textarea", full: true },
    { name: "reason", label: "Reason for the change", type: "textarea", required: true, full: true, help: "Kept in the record's history and the Activity Log." },
  ] : [
    { name: "date", label: `${record.stage} date`, type: "date", required: true, max: today() },
    { name: "owner", label: record.stage === "Screening" ? "Screening owner / recruiter" : "Reviewer (recruiter)", type: "select", required: true, allowNone: false,
      options: recruiters.map((r) => ({ value: r.name, label: r.name })) },
    { name: "remarks", label: ["Cleared", "Shortlisted"].includes(record.decision) ? "Remarks" : "Remarks (required for reject / hold)", type: "textarea", full: true },
    { name: "reason", label: "Reason for the change", type: "textarea", required: true, full: true, help: "Kept in the record's history and the Activity Log." },
  ];
  const initial = sel
    ? { selection_date: record.selection_date, decision_maker: record.decision_maker, compensation: record.compensation ?? "", remarks: record.remarks || "", reason: "" }
    : { date: record.date, owner: record.owner, remarks: record.remarks || "", reason: "" };
  return (
    <FormDialog open={open} onOpenChange={onOpenChange} title={`Edit ${record.stage.toLowerCase()} record`} testid="edit-record-form" submitLabel="Save changes"
      description={`Decision: ${record.decision} (not editable here — use Move stage to change it)`} fields={fields} initial={initial}
      onSubmit={async (v) => {
        try {
          if (sel) await api.put(`/selections/${record.id}`, { ...v, compensation: v.compensation === "" || v.compensation == null ? undefined : Number(v.compensation) });
          else await api.put(`/applications/${record.application_id}/stage-reviews/${record.id}`, v);
          toast.success("Record updated");
          onOpenChange(false);
          onSaved?.();
        } catch (e) { toast.error(errMsg(e)); }
      }} />
  );
}

/* The application's saved stage records, each with its stage date, owner and an Edit button. */
export function StageRecords({ app, onChanged }) {
  const { can } = useAuth();
  const [rows, setRows] = useState(null);
  const [edit, setEdit] = useState(null);
  const load = useCallback(async () => {
    const [{ data: reviews }, { data: sels }] = await Promise.all([
      api.get(`/applications/${app.id}/stage-reviews`), api.get("/selections", { params: { application_id: app.id } })]);
    const order = { Screening: 0, Shortlisting: 1, Selection: 2 };
    setRows([
      ...reviews.filter((r) => r.active).map((r) => ({ ...r, kind: "review", when: r.date, who: r.owner, whoLabel: "owner" })),
      ...sels.filter((s) => s.active !== false).slice(0, 1).map((s) => ({ ...s, kind: "selection", stage: "Selection", when: s.selection_date, who: s.decision_maker, whoLabel: "decision maker" })),
    ].sort((a, b) => order[a.stage] - order[b.stage]));
  }, [app.id]);
  useEffect(() => { load(); }, [load, app.status]);
  if (!rows?.length) return null;
  const canEdit = (r) => (r.kind === "selection" ? can("selection.decide") : can("app.move"));
  return (
    <div className="mt-4 border-t border-[#EEF1F5] pt-4" data-testid={`stage-records-${app.code}`}>
      <p className="mb-2 text-[11.5px] font-medium uppercase tracking-[0.04em] text-subtle">Stage records</p>
      <div className="divide-y divide-[#EEF1F5] rounded-[10px] border border-line">
        {rows.map((r) => {
          const last = r.edits?.at(-1);
          return (
            <div key={r.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2.5 text-[13px]" data-testid={`stage-record-${r.stage.toLowerCase()}`}>
              <span className="w-[96px] font-medium text-ink">{r.stage}</span>
              <span className="tabular-nums text-ink" data-testid="stage-record-date">{fmtDate(r.when)}</span>
              <span className="text-[#4B5361]">{r.decision}{r.kind === "selection" && r.compensation != null ? ` · ${lakhs(r.compensation)}` : ""}</span>
              <span className="text-[#4B5361]">{r.whoLabel}: {r.who || "—"}</span>
              <span className="text-[11.5px] text-subtle">recorded {fmtDateTime(r.created_at)}{last && <> · <span title={`${last.by}: ${last.reason}`} className="font-medium text-amber-800">edited {r.edits.length > 1 ? `${r.edits.length}×` : ""} by {last.by}</span></>}</span>
              {canEdit(r) && <Button size="sm" variant="ghost" className="ml-auto h-8" onClick={() => setEdit(r)} data-testid={`edit-${r.stage.toLowerCase()}`}><Pencil className="h-3.5 w-3.5" />Edit</Button>}
            </div>);
        })}
      </div>
      <EditRecordDialog open={!!edit} onOpenChange={(o) => !o && setEdit(null)} record={edit} onSaved={async () => { await load(); onChanged?.(); }} />
    </div>
  );
}
