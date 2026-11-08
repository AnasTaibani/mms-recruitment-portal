import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, Check, CircleDashed, Info, Loader2, ShieldAlert, X } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";
import { FormDialog, SelectField } from "@/components/common/FormDialog";
import { StatusBadge } from "@/components/common/StatusBadge";
import { FeedbackDialog, OfferDialog, ScheduleDialog, SelectionDialog } from "@/components/forms";
import { HireCostPanel } from "@/components/HireCost";
import { useAuth } from "@/context/AuthContext";
import { api, errMsg } from "@/lib/api";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

const today = () => new Date().toISOString().slice(0, 10);
const opts = (arr) => arr.map((s) => ({ value: s, label: s }));

/* Guided stage completion: shows what the requested stage needs, lets the user record each missing stage as a real
   record (screening / shortlisting review, interviews + feedback, selection, offer, cost reconciliation, joining),
   re-checks with the server after every save, and only then performs the move. Everything saved is kept if the
   wizard is closed part-way. */
export function StageWizard({ app, target, open, onClose, onDone, focus }) {
  const { user, can } = useAuth();
  const [rd, setRd] = useState(null);
  const [idx, setIdx] = useState(0);
  const [loading, setLoading] = useState(false);
  const [changed, setChanged] = useState(false);
  const [finished, setFinished] = useState(null);

  const load = useCallback(async (jumpToMissing = false) => {
    setLoading(true);
    try {
      const { data } = await api.get(`/applications/${app.id}/readiness`, { params: { target } });
      setRd(data);
      if (jumpToMissing) {
        const first = focus ? data.steps.findIndex((s) => s.key === focus) : data.steps.findIndex((s) => !s.done && s.blocking);
        setIdx(first === -1 ? data.steps.length : first);
      }
    } catch (e) { toast.error(errMsg(e)); } finally { setLoading(false); }
  }, [app?.id, target, focus]);

  useEffect(() => { if (open && app) { setFinished(null); setChanged(false); load(true); } }, [open, app, target, load]);

  const saved = async (advance = true) => {  // after any record is saved: re-check, move on to the next missing step
    setChanged(true);
    const { data } = await api.get(`/applications/${app.id}/readiness`, { params: { target } });
    setRd(data);
    if (advance) {
      const next = data.steps.findIndex((s) => !s.done && s.blocking);
      setIdx(next === -1 ? data.steps.length : next);
    }
  };
  const close = () => { onClose(); if (changed) onDone?.(); };

  if (!open || !app) return null;
  const steps = rd?.steps || [];
  const blocking = steps.filter((s) => s.blocking);
  const doneCount = blocking.filter((s) => s.done).length;
  const atSummary = idx >= steps.length;
  const step = steps[idx];
  const alreadyThere = rd && rd.current === target;

  return (
    <Dialog open={open} onOpenChange={(o) => !o && close()}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-4xl" data-testid="stage-wizard">
        <DialogHeader>
          <DialogTitle>Complete stages · move to “{target}”</DialogTitle>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-subtle">
            <span className="font-medium text-ink" data-testid="wizard-candidate">{app.candidate_name}</span>
            <span>{rd?.code || app.code}</span>
            <span className="flex items-center gap-1">Current <StatusBadge status={rd?.current || app.status} /></span>
            <ArrowRight className="h-3 w-3" />
            <span className="flex items-center gap-1">Requested <StatusBadge status={target} /></span>
          </div>
        </DialogHeader>

        {!rd ? <div className="flex h-40 items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-[#9AA2AE]" /></div> : finished ? (
          <Finished rd={finished} onClose={close} />
        ) : (
          <>
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs text-subtle"><span>{doneCount} of {blocking.length} required stage(s) complete</span>
                {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}</div>
              <Progress value={blocking.length ? (doneCount * 100) / blocking.length : 100} data-testid="wizard-progress" />
            </div>
            {!rd.transition_allowed && !alreadyThere && (
              <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800" data-testid="wizard-not-allowed">
                {rd.current} → {target} is not a permitted transition. Allowed from here: {rd.allowed_targets.join(", ") || "none"}.
              </div>
            )}
            <div className="grid gap-4 md:grid-cols-[220px_1fr]">
              <ol className="space-y-1" data-testid="wizard-steps">
                {steps.map((s, i) => (
                  <li key={s.key}>
                    <button type="button" onClick={() => setIdx(i)} data-testid={`wizard-step-${s.key}`}
                      className={cn("flex w-full items-start gap-2 rounded-lg px-2.5 py-2 text-left text-sm transition-colors", i === idx ? "bg-zinc-900/5 font-medium" : "hover:bg-zinc-900/[0.03]")}>
                      {s.done ? <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" /> : s.blocking ? <CircleDashed className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" /> : <Info className="mt-0.5 h-4 w-4 shrink-0 text-[#9AA2AE]" />}
                      <span>{s.stage}{!s.blocking && <span className="block text-[11px] font-normal text-[#9AA2AE]">not blocking</span>}{s.legacy && <span className="block text-[11px] font-normal text-[#9AA2AE]">historical record</span>}</span>
                    </button>
                  </li>
                ))}
                <li><button type="button" onClick={() => setIdx(steps.length)} data-testid="wizard-step-summary"
                  className={cn("flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm", atSummary ? "bg-zinc-900/5 font-medium" : "hover:bg-zinc-900/[0.03]")}>
                  <ArrowRight className="h-4 w-4 text-subtle" />Summary &amp; confirm</button></li>
              </ol>

              <div className="min-h-[260px] rounded-xl border border-line/80 bg-white/60 p-4">
                {atSummary
                  ? <Summary rd={rd} app={app} target={target} user={user} onMoved={async () => {
                      setChanged(true);
                      const { data } = await api.get(`/applications/${app.id}/readiness`, { params: { target } });
                      setFinished(data);
                    }} />
                  : <StepPanel step={step} app={app} rd={rd} user={user} can={can} onSaved={saved} />}
              </div>
            </div>
            <div className="flex items-center justify-between border-t border-line/70 pt-3">
              <p className="text-[11px] text-subtle">Each saved stage is kept as its own record — you can close and continue later.</p>
              <div className="flex gap-2">
                <Button variant="outline" onClick={close} data-testid="wizard-cancel"><X className="mr-1 h-4 w-4" />Cancel</Button>
                <Button variant="outline" disabled={idx === 0} onClick={() => setIdx(idx - 1)} data-testid="wizard-back"><ArrowLeft className="mr-1 h-4 w-4" />Back</Button>
                {!atSummary && <Button variant="outline" onClick={() => setIdx(idx + 1)} data-testid="wizard-next">Next<ArrowRight className="ml-1 h-4 w-4" /></Button>}
              </div>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Missing({ step }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-base font-semibold text-ink">{step.stage}</h3>
        <StatusBadge status={step.done ? "Complete" : step.blocking ? "Missing" : "Optional"} tone={step.done ? "green" : step.blocking ? "amber" : "zinc"} />
      </div>
      <p className="text-sm text-[#4B5361]" data-testid="wizard-step-summary-text">{step.summary}</p>
      {!step.done && step.missing.length > 0 && (
        <ul className="list-disc space-y-0.5 pl-5 text-xs text-amber-800" data-testid="wizard-missing">{step.missing.map((m) => <li key={m}>Missing: {m}</li>)}</ul>
      )}
    </div>
  );
}

function StepPanel({ step, app, rd, user, can, onSaved }) {
  if (!step) return null;
  const Comp = { screening: ReviewStep, shortlisting: ReviewStep, interviews: InterviewStep, selection: SelectionStep, offer: OfferStep, cost: CostStep, joining: JoiningStep }[step.key];
  return (
    <div className="space-y-4" data-testid={`wizard-panel-${step.key}`}>
      <Missing step={step} />
      {Comp && <Comp step={step} app={app} rd={rd} user={user} can={can} onSaved={onSaved} />}
    </div>
  );
}

/* ---- Screening / Shortlisting ---- */
function ReviewStep({ step, app, user, onSaved }) {
  const { list } = useAuth();
  const [open, setOpen] = useState(false);
  const screening = step.key === "screening";
  // every active recruiter (Master Data → Recruiters, incl. recruiter user accounts) is selectable
  const recruiters = list("recruiter").slice().sort((a, b) => a.name.localeCompare(b.name));
  const names = recruiters.map((r) => r.name);
  const defaultOwner = [app.recruiter, user.name].find((n) => n && names.includes(n));
  const fields = [
    { name: "date", label: `${step.stage} Date`, type: "date", required: true, max: today() },
    { name: "owner", label: screening ? "Screening Owner / Recruiter" : "Reviewer (Recruiter)", type: "select", required: true, allowNone: false,
      placeholder: recruiters.length ? "Select recruiter" : "No recruiters in Master Data",
      options: recruiters.map((r) => ({ value: r.name, label: r.designation ? `${r.name} — ${r.designation}` : r.name })) },
    { name: "decision", label: "Decision", type: "select", required: true, allowNone: false,
      options: opts(screening ? ["Cleared", "Rejected", "On Hold"] : ["Shortlisted", "Rejected", "On Hold"]) },
    { name: "remarks", label: "Remarks (required when rejecting or holding)", type: "textarea", full: true },
  ];
  if (step.done) return null;
  return (
    <>
      <Button onClick={() => setOpen(true)} data-testid={`wizard-record-${step.key}`}>Record {step.stage.toLowerCase()}</Button>
      <FormDialog open={open} onOpenChange={setOpen} title={`Record ${step.stage.toLowerCase()}`} description={`${app.candidate_name} · ${app.code}`}
        fields={fields} initial={{ date: today(), owner: defaultOwner, decision: screening ? "Cleared" : "Shortlisted" }} testid={`${step.key}-form`} submitLabel="Save & continue"
        onSubmit={async (v) => {
          try {
            await api.post(`/applications/${app.id}/stage-reviews`, { ...v, stage: step.stage });
            toast.success(`${step.stage} recorded`); setOpen(false);
            await onSaved(["Cleared", "Shortlisted"].includes(v.decision));
            if (!["Cleared", "Shortlisted"].includes(v.decision)) toast.info(`The application is now ${v.decision === "Rejected" ? "CV Rejected" : "On Hold"}`);
          } catch (e) { toast.error(errMsg(e)); }
        }} />
    </>
  );
}

/* ---- Interviews ---- */
function InterviewStep({ step, app, user, can, onSaved }) {
  const { mname } = useAuth();
  const [ivs, setIvs] = useState([]);
  const [dlg, setDlg] = useState(null);
  const [waiver, setWaiver] = useState("");
  const [override, setOverride] = useState({});
  const load = useCallback(async () => {
    const { data } = await api.get("/interviews", { params: { application_id: app.id } });
    setIvs(data);
  }, [app.id]);
  useEffect(() => { load(); }, [load]);
  const refresh = async () => { await load(); await onSaved(false); };
  const setStatus = async (iv, body, msg) => {
    try { await api.post(`/interviews/${iv.id}/status`, body); toast.success(msg); await refresh(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  const superAdmin = user.role === "super_admin";
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {can("interview.manage") && <Button size="sm" onClick={() => setDlg({ kind: "schedule" })} data-testid="wizard-schedule">Schedule a round</Button>}
      </div>
      {ivs.length > 0 && (
        <div className="divide-y divide-zinc-200/70 rounded-lg border border-line/70" data-testid="wizard-interviews">
          {[...ivs].sort((a, b) => (a.round_number || 0) - (b.round_number || 0)).map((iv) => {
            const pending = iv.feedback_pending || [];
            return (
              <div key={iv.id} className="space-y-2 p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">Round {iv.round_number} · {iv.round_name}</span>
                  <span className="text-xs text-subtle">{iv.date}</span>
                  <StatusBadge status={iv.status} /><StatusBadge status={`Feedback ${iv.feedback_status}`} tone="zinc" />
                  {iv.outcome && iv.outcome !== "Pending" && <StatusBadge status={iv.outcome} />}
                </div>
                {pending.length > 0 && !["Cancelled", "No Show"].includes(iv.status) && <p className="text-xs text-amber-700">Feedback pending from {pending.map((i) => mname(i) || i).join(", ")}</p>}
                {!["Cancelled", "No Show"].includes(iv.status) && (
                  <div className="flex flex-wrap items-center gap-2">
                    {pending.length > 0 && can("feedback.submit") && <Button size="sm" variant="outline" onClick={() => setDlg({ kind: "feedback", iv })} data-testid={`wizard-feedback-${iv.code}`}>Add feedback</Button>}
                    {iv.status !== "Completed" && pending.length === 0 && can("interview.manage") && <Button size="sm" variant="outline" onClick={() => setStatus(iv, { status: "Completed" }, "Interview completed")}>Mark completed</Button>}
                    {iv.status !== "Completed" && pending.length > 0 && superAdmin && (
                      <span className="flex items-center gap-1">
                        <Input className="h-8 w-56 text-xs" placeholder="Exception reason (Super Admin)" value={override[iv.id] || ""} onChange={(e) => setOverride({ ...override, [iv.id]: e.target.value })} data-testid={`wizard-iv-override-${iv.code}`} />
                        <Button size="sm" variant="outline" disabled={!(override[iv.id] || "").trim()} onClick={() => setStatus(iv, { status: "Completed", override_reason: override[iv.id] }, "Completed with exception")}>Complete anyway</Button>
                      </span>
                    )}
                    {iv.status === "Completed" && (can("interview.manage") || can("selection.decide")) && (
                      <SelectField value={null} onChange={(v) => v && setStatus(iv, { outcome: v }, `Recommendation: ${v}`)} options={opts(["Selected", "Rejected", "On Hold"])}
                        placeholder={iv.outcome && iv.outcome !== "Pending" ? `Recommendation: ${iv.outcome}` : "Final recommendation…"} testid={`wizard-outcome-${iv.code}`} className="w-52" />
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      {!step.done && superAdmin && (
        <div className="space-y-2 rounded-lg border border-amber-200 bg-amber-50/70 p-3" data-testid="wizard-waiver">
          <p className="flex items-center gap-1.5 text-xs font-semibold text-amber-900"><ShieldAlert className="h-3.5 w-3.5" />Authorised waiver (Super Admin)</p>
          <Textarea rows={2} placeholder="Why are the interviews being waived? (recorded in the audit trail)" value={waiver} onChange={(e) => setWaiver(e.target.value)} data-testid="wizard-waiver-reason" />
          <Button size="sm" variant="outline" disabled={!waiver.trim()} data-testid="wizard-waiver-save" onClick={async () => {
            try { await api.post(`/applications/${app.id}/interview-waiver`, { reason: waiver }); toast.success("Interview waiver recorded"); setWaiver(""); await onSaved(true); }
            catch (e) { toast.error(errMsg(e)); }
          }}>Record waiver</Button>
        </div>
      )}
      <ScheduleDialog open={dlg?.kind === "schedule"} onOpenChange={(o) => !o && setDlg(null)} application={app} onDone={refresh} />
      <FeedbackDialog open={dlg?.kind === "feedback"} onOpenChange={(o) => !o && setDlg(null)} interview={dlg?.iv} onDone={refresh} />
    </div>
  );
}

/* ---- Selection ---- */
function SelectionStep({ step, app, can, onSaved }) {
  const [open, setOpen] = useState(false);
  if (step.done || !can("selection.decide")) return step.done ? null : <p className="text-xs text-subtle">You do not have permission to record selection decisions.</p>;
  return (
    <>
      <Button onClick={() => setOpen(true)} data-testid="wizard-record-selection">Record selection decision</Button>
      <SelectionDialog open={open} onOpenChange={setOpen} app={app} onDone={() => onSaved(true)} />
    </>
  );
}

/* ---- Offer: create → submit → approve → release → accept ---- */
function OfferStep({ step, app, rd, can, onSaved }) {
  const [offers, setOffers] = useState([]);
  const [create, setCreate] = useState(false);
  const [date, setDate] = useState(today());
  const [tentative, setTentative] = useState("");
  const [reason, setReason] = useState("");
  const load = useCallback(async () => {
    const { data } = await api.get("/offers", { params: { candidate_id: app.candidate_id } });
    setOffers(data.filter((o) => o.application_id === app.id));
  }, [app.id, app.candidate_id]);
  useEffect(() => { load(); }, [load]);
  const current = offers.find((o) => ["Draft", "Approval Pending", "Approved", "Released", "Accepted"].includes(o.status));
  const act = async (action, extra = {}) => {
    try {
      await api.post(`/offers/${current.id}/action`, { action, ...extra });
      toast.success(`Offer ${action === "submit" ? "submitted for approval" : action + "d"}`.replace("released", "released").replace("acceptd", "accepted").replace("rejectd", "rejected"));
      setReason(""); await load(); await onSaved(action === "accept" || action === "release");
    } catch (e) { toast.error(errMsg(e)); }
  };
  const target = rd.target;
  const enough = step.done;
  return (
    <div className="space-y-3">
      {offers.length > 0 && (
        <div className="flex flex-wrap gap-2 text-xs text-[#4B5361]">{offers.map((o) => <span key={o.id} className="rounded-md border border-line px-2 py-1">{o.code} · ₹{o.ctc} L · {o.status}</span>)}</div>
      )}
      {!current && can("offer.manage") && <Button onClick={() => setCreate(true)} data-testid="wizard-create-offer">{offers.length ? "Create re-offer" : "Create offer"}</Button>}
      {current && !enough && (
        <div className="space-y-3 rounded-lg border border-line/70 p-3 text-sm">
          <p className="font-medium">{current.code} is <StatusBadge status={current.status} /></p>
          {current.status === "Draft" && can("offer.manage") && <Button size="sm" onClick={() => act("submit")} data-testid="wizard-offer-submit">Submit for approval</Button>}
          {current.status === "Approval Pending" && (can("offer.approve") ? (
            <div className="flex flex-wrap items-end gap-2">
              <Button size="sm" onClick={() => act("approve")} data-testid="wizard-offer-approve">Approve</Button>
              <Input className="h-8 w-60 text-xs" placeholder="Reason (to reject)" value={reason} onChange={(e) => setReason(e.target.value)} />
              <Button size="sm" variant="outline" disabled={!reason.trim()} onClick={() => act("reject", { reason })}>Reject</Button>
            </div>) : <p className="text-xs text-subtle">Waiting for an approver.</p>)}
          {["Approved", "Released"].includes(current.status) && can("offer.manage") && (
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="space-y-1"><Label className="text-xs">{current.status === "Approved" ? "Release date" : "Acceptance date"} *</Label>
                <Input type="date" max={today()} value={date} onChange={(e) => setDate(e.target.value)} data-testid="wizard-offer-date" /></div>
              {current.status === "Released" && <div className="space-y-1"><Label className="text-xs">Tentative joining date</Label>
                <Input type="date" value={tentative} onChange={(e) => setTentative(e.target.value)} data-testid="wizard-offer-tentative" /></div>}
              <div className="sm:col-span-2">
                {current.status === "Approved"
                  ? <Button size="sm" disabled={!date} onClick={() => act("release", { date })} data-testid="wizard-offer-release">Release offer</Button>
                  : <Button size="sm" disabled={!date || target === "Offer Released"} onClick={() => act("accept", { date, tentative_joining_date: tentative || null })} data-testid="wizard-offer-accept">Record acceptance</Button>}
              </div>
            </div>
          )}
        </div>
      )}
      <OfferDialog open={create} onOpenChange={setCreate} app={app} onDone={async () => { await load(); await onSaved(false); }} />
    </div>
  );
}

/* ---- Recruitment cost confirmation (required before Joined) ---- */
function CostStep({ app, onSaved }) {
  return <HireCostPanel app={app} compact onSaved={() => onSaved(true)} />;
}

/* ---- Joining ---- */
function JoiningStep({ step, app, can, onSaved }) {
  const [j, setJ] = useState(null);
  const [tentative, setTentative] = useState("");
  const load = useCallback(async () => {
    const { data } = await api.get("/joinings", { params: { requisition_id: app.requisition_id } });
    setJ(data.find((x) => x.application_id === app.id && !["Cancelled", "No Show"].includes(x.status)) || null);
  }, [app.id, app.requisition_id]);
  useEffect(() => { load(); }, [load, step.done]);
  if (step.done) return null;
  if (!j) return (
    <div className="space-y-2 text-sm">
      <p className="text-[#4B5361]">The joining record is created when the offer is accepted.</p>
      {app.status === "Offer Accepted" && can("joining.manage") && (
        <div className="flex items-end gap-2">
          <div className="space-y-1"><Label className="text-xs">Tentative joining date</Label><Input type="date" value={tentative} onChange={(e) => setTentative(e.target.value)} /></div>
          <Button size="sm" onClick={async () => { try { await api.post("/joinings", { application_id: app.id, tentative_date: tentative || null }); toast.success("Joining record created"); await load(); await onSaved(false); } catch (e) { toast.error(errMsg(e)); } }}>Create joining record</Button>
        </div>
      )}
    </div>
  );
  const got = (j.checklist || []).filter((c) => c.received).length;
  return (
    <div className="space-y-1 text-sm text-[#4B5361]" data-testid="wizard-joining-info">
      <p>{j.code} · {j.status}{j.tentative_date && ` · tentative ${j.tentative_date}`}{j.confirmed_date && ` · confirmed ${j.confirmed_date}`}</p>
      <p>Document checklist: {got}/{(j.checklist || []).length} received ({j.checklist_status || "—"}) — manage it on the Joining page.</p>
      <p className="text-xs text-subtle">Enter the actual date of joining on the summary step to complete the move.</p>
    </div>
  );
}

/* ---- Summary & confirm ---- */
function Summary({ rd, app, target, user, onMoved }) {
  const [date, setDate] = useState("");
  const [override, setOverride] = useState("");
  const [busy, setBusy] = useState(false);
  // for Joined, an existing joining record is completed here with the actual date of joining
  const blockingMissing = rd.steps.filter((s) => s.blocking && !s.done && !(target === "Joined" && s.key === "joining" && s.record_ids.length));
  const needsJoinDate = target === "Joined";
  const ready = rd.transition_allowed && blockingMissing.length === 0;
  const recordBacked = ["Selected", "Offer Approval Pending", "Offer Released", "Offer Accepted", "Joined"].includes(target);
  const canOverride = user.role === "super_admin" && rd.transition_allowed && !recordBacked && blockingMissing.length > 0;
  const already = rd.current === target;
  const move = async (withOverride) => {
    setBusy(true);
    try {
      const { data } = await api.post(`/applications/${app.id}/status`, { status: target, joining_date: needsJoinDate ? date : undefined, override_reason: withOverride ? override : undefined });
      toast.success(`Moved to ${target}`);
      await onMoved(data);
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-4" data-testid="wizard-summary">
      <h3 className="text-base font-semibold text-ink">Summary</h3>
      <ul className="space-y-1.5 text-sm">
        {rd.steps.map((s) => (
          <li key={s.key} className="flex items-start gap-2">
            {s.done ? <Check className="mt-0.5 h-4 w-4 text-emerald-600" /> : <CircleDashed className={cn("mt-0.5 h-4 w-4", s.blocking ? "text-amber-600" : "text-[#9AA2AE]")} />}
            <span><span className="font-medium">{s.stage}:</span> {s.summary}</span>
          </li>
        ))}
      </ul>
      {already ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800" data-testid="wizard-already">The application is now at “{target}”. The pipeline has been updated.</div>
      ) : (
        <>
          {blockingMissing.length > 0 && <p className="text-sm text-amber-800" data-testid="wizard-blocked">Complete: {blockingMissing.map((s) => s.stage).join(", ")} before confirming.</p>}
          {needsJoinDate && (
            <div className="max-w-xs space-y-1"><Label className="text-xs">Actual date of joining *</Label>
              <Input type="date" max={today()} value={date} onChange={(e) => setDate(e.target.value)} data-testid="wizard-join-date" /></div>
          )}
          <Button disabled={!ready || busy || (needsJoinDate && !date)} onClick={() => move(false)} data-testid="wizard-confirm">
            {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Confirm move to {target}</Button>
          {canOverride && (
            <div className="space-y-2 rounded-lg border border-amber-200 bg-amber-50/70 p-3" data-testid="wizard-override">
              <p className="flex items-center gap-1.5 text-xs font-semibold text-amber-900"><ShieldAlert className="h-3.5 w-3.5" />Authorised exception (Super Admin)</p>
              <Textarea rows={2} placeholder="Reason for moving without the missing stages (recorded in the audit trail)" value={override} onChange={(e) => setOverride(e.target.value)} data-testid="wizard-override-reason" />
              <Button size="sm" variant="outline" disabled={!override.trim() || busy} onClick={() => move(true)} data-testid="wizard-override-confirm">Move with exception</Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Finished({ rd, onClose }) {
  return (
    <div className="space-y-4 py-2" data-testid="wizard-finished">
      <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
        <p className="font-semibold">Stage updated to “{rd.target}”.</p>
        <p className="mt-1 text-xs">The pipeline and the activity history have been updated with each record created.</p>
      </div>
      <ul className="space-y-1 text-sm">{rd.steps.map((s) => <li key={s.key} className="flex gap-2"><Check className="mt-0.5 h-4 w-4 text-emerald-600" /><span><span className="font-medium">{s.stage}:</span> {s.summary}</span></li>)}</ul>
      <div className="flex justify-end"><Button onClick={onClose} data-testid="wizard-done">Done</Button></div>
    </div>
  );
}
