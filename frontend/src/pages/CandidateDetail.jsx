import { useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { FileText, Pencil, Plus, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/context/AuthContext";
import { useFetch } from "@/lib/useFetch";
import { Info, PageHeader, Section, Timeline } from "@/components/common/Page";
import { StatusBadge } from "@/components/common/StatusBadge";
import { FormDialog } from "@/components/common/FormDialog";
import { EmptyState } from "@/components/common/DataTable";
import { AppActions } from "@/components/AppActions";
import { CandidateDialog } from "@/components/forms";
import { HistoryTab } from "@/pages/RequisitionDetail";
import { api, download, errMsg, fmtDate, fmtDateTime, lakhs } from "@/lib/api";
import { toast } from "sonner";

function ApplyDialog({ open, onOpenChange, cand, onDone }) {
  const { data } = useFetch("/requisitions", { status: "Open" }, open);
  return (
    <FormDialog open={open} onOpenChange={onOpenChange} title="Add to requisition" description={cand.name} testid="apply-form" submitLabel="Add application"
      fields={[{ name: "requisition_id", label: "Open requisition", type: "select", required: true, options: (data || []).map((r) => ({ value: r.id, label: `${r.code} · ${r.title}` })) }]}
      onSubmit={async (v) => { try { await api.post("/applications", { candidate_id: cand.id, requisition_id: v.requisition_id }); toast.success("Application created"); onOpenChange(false); onDone(); } catch (e) { toast.error(errMsg(e)); } }} />
  );
}

function Applications({ c, reload }) {
  if (!c.applications.length) return <EmptyState title="No applications" hint="Add this candidate to an open requisition." />;
  return (
    <div className="space-y-3">
      {c.applications.map((a) => (
        <Section key={a.id} testid={`application-${a.code}`}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="font-mono text-[11px] text-zinc-400">{a.code} · {a.requisition_code}</p>
              <Link to={`/requisitions/${a.requisition_id}`} className="text-base font-semibold text-zinc-900 hover:underline">{a.requisition_title}</Link>
              <p className="text-xs text-zinc-500">{a.department || "—"} · Recruiter {a.recruiter || "—"} · {a.days_in_stage} day(s) in stage {a.stuck && <b className="text-amber-700">· stuck</b>}</p>
              {a.status === "Joined" && <p className="mt-1 text-xs" data-testid={`application-cost-${a.code}`}>Recruitment cost: {a.cost_status
                ? <b className="text-zinc-700">{a.cost_status}</b> : <b className="text-amber-700">not reconciled</b>}</p>}
              {a.interview_waiver && <p className="mt-1 text-xs text-amber-800">Interviews waived by {a.interview_waiver.by}: {a.interview_waiver.reason}</p>}
            </div>
            <div className="flex items-center gap-2"><StatusBadge status={a.status} testid={`application-status-${a.code}`} /><AppActions app={a} onDone={reload} /></div>
          </div>
          <div className="mt-4 border-t border-zinc-100 pt-4">
            <Timeline items={[...(a.history || [])].reverse().map((h) => ({ title: h.from ? `${h.from} → ${h.status}` : h.status, details: [h.reason, h.note, h.override && `EXCEPTION: ${h.override_reason}`].filter(Boolean).join(" · "), meta: `${h.by}${h.auto ? " (automatic)" : ""} · ${fmtDateTime(h.at)}` }))} />
          </div>
        </Section>
      ))}
    </div>
  );
}

export default function CandidateDetail() {
  const { id } = useParams();
  const { can } = useAuth();
  const { data: c, reload } = useFetch(`/candidates/${id}`);
  const [dlg, setDlg] = useState(null);
  const fileRef = useRef();
  if (!c) return <p className="text-sm text-zinc-400">Loading…</p>;
  const upload = async (file) => {
    if (!file) return;
    const fd = new FormData();
    fd.append("entity", "candidate"); fd.append("entity_id", id); fd.append("file", file);
    try { await api.post("/files", fd); toast.success("Resume uploaded"); reload(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div>
      <PageHeader eyebrow={c.code} title={c.name} description={[c.current_designation, c.current_company, c.current_location].filter(Boolean).join(" · ")}
        actions={<>
          {c.resume && <Button variant="outline" onClick={() => download(`/files/${c.resume.file_id}`)} data-testid="cand-resume-download"><FileText className="mr-2 h-4 w-4" />Resume</Button>}
          {can("cand.manage") && <><input ref={fileRef} type="file" accept=".pdf,.docx,.doc" hidden onChange={(e) => upload(e.target.files[0])} data-testid="cand-resume-input" />
            <Button variant="outline" onClick={() => fileRef.current.click()} data-testid="cand-resume-upload"><Upload className="mr-2 h-4 w-4" />Upload CV</Button>
            <Button variant="outline" onClick={() => setDlg("apply")} data-testid="cand-apply-btn"><Plus className="mr-2 h-4 w-4" />Add to requisition</Button>
            <Button onClick={() => setDlg("edit")} data-testid="cand-edit-btn"><Pencil className="mr-2 h-4 w-4" />Edit</Button></>}
        </>} />
      <Tabs defaultValue="applications">
        <TabsList className="flex-wrap">
          <TabsTrigger value="applications" data-testid="tab-applications">Applications ({c.applications.length})</TabsTrigger>
          <TabsTrigger value="profile" data-testid="tab-profile">Profile</TabsTrigger>
          <TabsTrigger value="interviews" data-testid="tab-interviews">Interviews ({c.interviews.length})</TabsTrigger>
          {can("offer.view") && <TabsTrigger value="offers" data-testid="tab-offers">Offers & Joining</TabsTrigger>}
          <TabsTrigger value="activity" data-testid="tab-activity">Activity</TabsTrigger>
        </TabsList>
        <TabsContent value="applications"><Applications c={c} reload={reload} /></TabsContent>
        <TabsContent value="profile">
          <Section><div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            <Info label="Email">{c.email}</Info><Info label="Mobile">{c.phone}</Info><Info label="Total experience">{c.total_exp != null && `${c.total_exp} yrs`}</Info><Info label="Relevant experience">{c.relevant_exp != null && `${c.relevant_exp} yrs`}</Info>
            <Info label="Qualification">{c.qualification}</Info><Info label="Current CTC">{lakhs(c.current_ctc)}</Info><Info label="Expected CTC">{lakhs(c.expected_ctc)}</Info><Info label="Notice period">{c.notice_period}</Info>
            <Info label="Last working day">{fmtDate(c.last_working_day)}</Info><Info label="Available from">{fmtDate(c.available_from)}</Info><Info label="Source">{c.source}</Info><Info label="Recruitment partner">{c.partner}</Info>
            <Info label="Recruiter">{c.recruiter}</Info><Info label="Resume">{c.resume ? c.resume.name : null}</Info><Info label="Created">{fmtDateTime(c.created_at)}</Info><Info label="Updated">{fmtDateTime(c.updated_at)}</Info>
            <div className="sm:col-span-4"><Info label="Remarks">{c.remarks}</Info></div>
          </div></Section>
        </TabsContent>
        <TabsContent value="interviews">
          <Section>{!c.interviews.length ? <EmptyState title="No interviews" /> : c.interviews.map((i) => (
            <div key={i.id} className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-100 py-3 last:border-0">
              <div><p className="text-sm font-medium">Round {i.round_number} · {i.round_name}</p><p className="text-xs text-zinc-500">{i.code} · {fmtDate(i.date)} {i.start_time || ""} · {i.mode || "—"}</p></div>
              <div className="flex gap-2"><StatusBadge status={i.status} /><StatusBadge status={i.outcome} /></div>
            </div>))}</Section>
        </TabsContent>
        <TabsContent value="offers">
          <div className="grid gap-4 lg:grid-cols-2">
            <Section title="Offers">{!c.offers.length ? <EmptyState title="No offers" /> : c.offers.map((o) => (
              <div key={o.id} className="flex items-center justify-between border-b border-zinc-100 py-2.5 last:border-0"><div><p className="text-sm font-medium">{o.designation} · {lakhs(o.ctc)}</p><p className="text-xs text-zinc-500">{o.code} · valid until {fmtDate(o.validity_date)}</p></div><StatusBadge status={o.status} /></div>))}</Section>
            <Section title="Joining">{!c.joinings.length ? <EmptyState title="No joining records" /> : c.joinings.map((j) => (
              <div key={j.id} className="flex items-center justify-between border-b border-zinc-100 py-2.5 last:border-0"><div><p className="text-sm font-medium">{j.code}</p><p className="text-xs text-zinc-500">Tentative {fmtDate(j.tentative_date)} · Actual {fmtDate(j.actual_date)}</p></div><StatusBadge status={j.status} /></div>))}</Section>
          </div>
        </TabsContent>
        <TabsContent value="activity"><Section><HistoryTab entity="candidate" id={id} /></Section></TabsContent>
      </Tabs>
      <CandidateDialog open={dlg === "edit"} onOpenChange={(o) => !o && setDlg(null)} initial={c} onSaved={reload} />
      <ApplyDialog open={dlg === "apply"} onOpenChange={(o) => !o && setDlg(null)} cand={c} onDone={reload} />
    </div>
  );
}
