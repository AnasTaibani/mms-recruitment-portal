import { useCallback, useEffect, useState } from "react";
import { Loader2, Pencil } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, errMsg, fmtDateTime, lakhs } from "@/lib/api";
import { toast } from "sonner";

const FIELDS = [
  ["ctc", "Candidate annual CTC", "Must be more than 0"],
  ["consulting_fee", "Consulting fees", "Recruitment partner / consultancy — enter 0 if none"],
  ["recruiter_fee", "Recruiter fees", "External recruiter — enter 0 if none"],
];
const PCT = { consulting_fee: "consulting_fee_pct", recruiter_fee: "recruiter_fee_pct" };
const feeFromPct = (ctc, pct) => (ctc === "" || pct === "" || Number.isNaN(Number(ctc)) || Number.isNaN(Number(pct)) ? "" : String(Math.round(Number(ctc) * Number(pct) * 100) / 10000));
const rupees = (v) => (v === "" || v == null || Number.isNaN(Number(v)) ? "" : `₹${Math.round(Number(v) * 100000).toLocaleString("en-IN")}`);

// Same rules as the server: blank is not zero, no negatives, CTC > 0, amounts in ₹ lakhs.
export function checkHireCost(v) {
  const errors = {};
  FIELDS.forEach(([k, label]) => {
    const raw = v[k];
    if (raw === "" || raw === null || raw === undefined) errors[k] = `${label} is required${k === "ctc" ? "" : " (enter 0 if none)"}`;
    else if (Number.isNaN(Number(raw))) errors[k] = "Enter a number";
    else if (Number(raw) < 0) errors[k] = "Cannot be negative";
    else if (Number(raw) > 1000) errors[k] = "Enter in ₹ lakhs — e.g. 6 for ₹6,00,000";
  });
  if (!errors.ctc && Number(v.ctc) <= 0) errors.ctc = "Annual CTC must be greater than zero";
  Object.entries(PCT).forEach(([k, p]) => {
    const raw = v[p];
    if (raw === "" || raw == null) return;
    if (Number.isNaN(Number(raw)) || Number(raw) < 0 || Number(raw) > 100) errors[k] = "Fee % must be between 0 and 100";
  });
  return errors;
}

/* Recruitment cost confirmation for one application: annual CTC + consulting fees + recruiter fees = cost per hire. */
export function HireCostPanel({ app, onSaved, compact }) {
  const [data, setData] = useState(null);
  const [editing, setEditing] = useState(false);
  const [v, setV] = useState({ ctc: "", consulting_fee: "", recruiter_fee: "", consulting_fee_pct: "", recruiter_fee_pct: "" });
  const [reason, setReason] = useState("");
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try {
      const { data: d } = await api.get(`/applications/${app.id}/hire-cost`);
      setData(d);
      const base = d.hire_cost || d.suggested || {};
      setV({ ctc: base.ctc ?? "", consulting_fee: base.consulting_fee ?? "", recruiter_fee: base.recruiter_fee ?? "",
        consulting_fee_pct: base.consulting_fee_pct ?? "", recruiter_fee_pct: base.recruiter_fee_pct ?? "" });
      setEditing(!d.hire_cost);
    } catch (e) { toast.error(errMsg(e)); }
  }, [app.id]);
  useEffect(() => { load(); }, [load]);
  if (!data) return <Loader2 className="h-4 w-4 animate-spin text-[#9AA2AE]" />;
  const hc = data.hire_cost;
  const errors = checkHireCost(v);
  const valid = !Object.keys(errors).length;
  const total = valid ? Math.round((Number(v.ctc) + Number(v.consulting_fee) + Number(v.recruiter_fee)) * 10000) / 10000 : null;
  const canConfirm = ["Offer Accepted", "Joined"].includes(data.status);
  const setCtc = (ctc) => {
    const next = { ...v, ctc };
    Object.entries(PCT).forEach(([k, p]) => { if (v[p] !== "" && v[p] != null) next[k] = feeFromPct(ctc, v[p]); });
    setV(next);
  };
  const setPct = (k, pct) => setV({ ...v, [PCT[k]]: pct, [k]: pct === "" ? v[k] : feeFromPct(v.ctc, pct) });
  const setAmount = (k, amt) => setV({ ...v, [k]: amt, [PCT[k]]: "" });
  const save = async () => {
    setTouched(true);
    if (!valid || (hc && !reason.trim())) return;
    setBusy(true);
    try {
      const pct = (p) => (v[p] === "" || v[p] == null ? null : Number(v[p]));
      await api.put(`/applications/${app.id}/hire-cost`, { ctc: Number(v.ctc), consulting_fee: Number(v.consulting_fee), recruiter_fee: Number(v.recruiter_fee),
        consulting_fee_pct: pct("consulting_fee_pct"), recruiter_fee_pct: pct("recruiter_fee_pct"), currency: "INR", ctc_basis: "annual", reason: hc ? reason : undefined });
      toast.success(hc ? "Cost details updated" : "Recruitment cost confirmed");
      setReason(""); setTouched(false);
      await load();
      await onSaved?.();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-4" data-testid="hire-cost-panel">
      <p className="text-xs text-subtle">Cost per Hire = Candidate annual CTC + Consulting fees + Recruiter fees. Fee = CTC × Fee % ÷ 100 when a % is entered. All amounts in ₹ lakhs (INR). Required before the candidate is marked Joined.</p>
      {hc && !editing ? (
        <div className="space-y-3">
          <Breakdown hc={hc} />
          <p className="text-[11px] text-subtle" data-testid="hire-cost-confirmed">Confirmed by {hc.confirmed_by} · {fmtDateTime(hc.confirmed_at)}
            {hc.version > 1 && ` · last changed by ${hc.updated_by} · ${fmtDateTime(hc.updated_at)}`}</p>
          {data.can_edit && <Button size="sm" variant="outline" onClick={() => setEditing(true)} data-testid="hire-cost-edit"><Pencil className="mr-1.5 h-3.5 w-3.5" />Change cost details</Button>}
        </div>
      ) : !data.can_edit ? (
        <p className="text-sm text-amber-800">Recruitment cost is not confirmed yet. A Recruiter (HR) or Super Admin confirms it.</p>
      ) : !canConfirm ? (
        <p className="text-sm text-[#4B5361]">The cost is confirmed once the offer is accepted (current stage: {data.status}).</p>
      ) : (
        <div className="space-y-3">
          {!hc && data.suggested?.ctc_source && <p className="text-[11px] text-subtle">CTC pre-filled from the {data.suggested.ctc_source}{(data.suggested.consulting_fee != null || data.suggested.recruiter_fee != null) && "; fees from recorded cost entries"} — check before confirming.</p>}
          <div className={compact ? "grid gap-3 sm:grid-cols-3" : "grid gap-3 sm:grid-cols-3"}>
            {FIELDS.map(([k, label, hint]) => {
              const p = PCT[k], hasPct = p && v[p] !== "" && v[p] != null;
              const msg = touched && errors[k] ? errors[k]
                : hasPct && v[k] !== "" ? `${v[p]}% of ${lakhs(Number(v.ctc))} = ${rupees(v[k])}` : rupees(v[k]) || (p ? `${hint}, or enter a fee %` : hint);
              return (
                <div key={k} className="space-y-1">
                  <Label className="text-xs">{label} (₹ L) *</Label>
                  <div className="flex gap-1.5">
                    {p && (
                      <div className="relative w-[76px] shrink-0">
                        <Input type="number" step="any" min="0" max="100" value={v[p]} placeholder="Fee" aria-label={`${label} — fee % of CTC`}
                          onChange={(e) => setPct(k, e.target.value)} onBlur={() => setTouched(true)} className="pr-6" data-testid={`hire-cost-${k}-pct`} />
                        <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-xs text-subtle">%</span>
                      </div>
                    )}
                    <Input type="number" step="any" min="0" value={v[k]} onBlur={() => setTouched(true)} data-testid={`hire-cost-${k}`} aria-label={`${label} amount in lakhs`}
                      onChange={(e) => (k === "ctc" ? setCtc(e.target.value) : setAmount(k, e.target.value))} className={hasPct ? "bg-canvas" : undefined} />
                  </div>
                  <p className={`text-[11px] ${touched && errors[k] ? "text-rose-600" : "text-[#9AA2AE]"}`} data-testid={`hire-cost-${k}-msg`}>{msg}</p>
                </div>
              );
            })}
          </div>
          <div className="flex items-center justify-between rounded-lg border border-line/80 bg-zinc-900/[0.02] px-3 py-2">
            <span className="text-sm text-[#4B5361]">Cost per Hire</span>
            <span className="text-base font-semibold text-ink" data-testid="hire-cost-total">{total === null ? "—" : `${lakhs(total)} · ${rupees(total)}`}</span>
          </div>
          {hc && (
            <div className="space-y-1"><Label className="text-xs">Reason for the change *</Label>
              <Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} data-testid="hire-cost-reason" />
              {touched && !reason.trim() && <p className="text-[11px] text-rose-600">A reason is required to change confirmed cost details</p>}</div>
          )}
          <div className="flex gap-2">
            <Button size="sm" disabled={busy} onClick={save} data-testid="hire-cost-confirm">{busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}{hc ? "Save changes" : "Confirm cost"}</Button>
            {hc && <Button size="sm" variant="outline" onClick={() => { setEditing(false); load(); }}>Cancel</Button>}
          </div>
        </div>
      )}
      {data.history?.length > 0 && !compact && (
        <div>
          <p className="eyebrow mb-1.5">Cost history</p>
          <ul className="space-y-1.5 text-xs text-[#4B5361]" data-testid="hire-cost-history">
            {[...data.history].reverse().map((h, i) => (
              <li key={i} className="rounded-md border border-line/70 px-2.5 py-1.5">
                <b>{h.action}</b> by {h.by} · {fmtDateTime(h.at)}
                <div>{h.previous && <span className="text-[#9AA2AE] line-through">{lakhs(h.previous.total)}</span>} {lakhs(h.new.total)}
                  <span className="text-[#9AA2AE]"> (CTC {lakhs(h.new.ctc)} + consulting {lakhs(h.new.consulting_fee)} + recruiter {lakhs(h.new.recruiter_fee)})</span></div>
                {h.reason && <div className="italic">“{h.reason}”</div>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Breakdown({ hc }) {
  return (
    <table className="w-full max-w-md text-sm" data-testid="hire-cost-breakdown">
      <tbody>
        {[["Candidate annual CTC", hc.ctc], [`Consulting fees${hc.consulting_fee_pct != null ? ` (${hc.consulting_fee_pct}%)` : ""}`, hc.consulting_fee],
          [`Recruiter fees${hc.recruiter_fee_pct != null ? ` (${hc.recruiter_fee_pct}%)` : ""}`, hc.recruiter_fee]].map(([l, x]) => (
          <tr key={l}><td className="py-0.5 text-[#4B5361]">{l}</td><td className="py-0.5 text-right">{lakhs(x)}</td><td className="py-0.5 pl-3 text-right text-xs text-[#9AA2AE]">{rupees(x)}</td></tr>
        ))}
        <tr className="border-t border-line font-semibold"><td className="pt-1">Cost per Hire</td><td className="pt-1 text-right">{lakhs(hc.total)}</td><td className="pt-1 pl-3 text-right text-xs text-subtle">{rupees(hc.total)}</td></tr>
      </tbody>
    </table>
  );
}

export function HireCostDialog({ app, open, onOpenChange, onDone }) {
  if (!app) return null;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl" data-testid="hire-cost-dialog">
        <DialogHeader><DialogTitle>Recruitment cost · {app.candidate_name}</DialogTitle>
          <p className="text-xs text-subtle">{app.code} · {app.requisition_title}</p></DialogHeader>
        <HireCostPanel app={app} onSaved={onDone} />
      </DialogContent>
    </Dialog>
  );
}
