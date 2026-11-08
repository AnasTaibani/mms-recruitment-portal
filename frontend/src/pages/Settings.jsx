import { useEffect, useState } from "react";
import { Plus, Pencil, Loader2, Trash2, ShieldAlert, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/context/AuthContext";
import { useFetch } from "@/lib/useFetch";
import { PageHeader, Section } from "@/components/common/Page";
import { DataTable } from "@/components/common/DataTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { FormDialog, SelectField } from "@/components/common/FormDialog";
import { api, errMsg } from "@/lib/api";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

const PERSON = ["recruiter", "hiring_manager", "interviewer"];

function Masters() {
  const { meta, list, reloadRef, can } = useAuth();
  const [type, setType] = useState("department");
  const [edit, setEdit] = useState(null);
  const { data: users } = useFetch("/users", {}, can("users.manage"));
  const rows = list(type, true);
  const person = PERSON.includes(type);
  const fields = [{ name: "name", label: "Name", required: true }, ...(person || type === "partner" ? [{ name: "email", label: "Email" }, { name: "phone", label: "Phone" }] : []),
    ...(type === "interviewer" ? [{ name: "skill_area", label: "Skill area(s)" }] : []),
    ...(person ? [{ name: "user_id", label: "Linked portal user", type: "select", options: (users || []).map((u) => ({ value: u.id, label: `${u.name} (${u.role_label})` })), help: "Grants this user record-level access as this person" }] : []),
    { name: "notes", label: "Notes", type: "textarea" }];
  const save = async (v) => {
    try { edit.id ? await api.put(`/masters/${edit.id}`, v) : await api.post("/masters", { ...v, type }); toast.success("Saved"); setEdit(null); reloadRef(); } catch (e) { toast.error(errMsg(e)); }
  };
  const toggle = async (m) => { try { await api.put(`/masters/${m.id}`, { active: !m.active }); reloadRef(); } catch (e) { toast.error(errMsg(e)); } };
  const userName = (id) => (users || []).find((u) => u.id === id)?.name;
  return (
    <div className="grid gap-4 lg:grid-cols-[240px_1fr]">
      <div className="space-y-0.5 rounded-xl border border-line bg-white p-2">
        {Object.entries(meta.master_types).map(([k, l]) => (
          <button key={k} onClick={() => setType(k)} data-testid={`master-type-${k}`} className={cn("flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm", type === k ? "bg-brand-deep text-white" : "hover:bg-[#EEF1F5]")}>
            {l}<span className="text-[11px] opacity-60">{list(k, true).length}</span></button>))}
      </div>
      <DataTable key={type} testid="master-table" data={rows} toolbar={<Button size="sm" className="h-9" onClick={() => setEdit({})} data-testid="master-add-btn"><Plus className="mr-1.5 h-4 w-4" />Add</Button>}
        columns={[{ key: "name", label: meta.master_types[type], render: (m) => <span className="font-medium text-ink">{m.name}</span> },
          ...(person || type === "partner" ? [{ key: "email", label: "Email" }] : []), ...(type === "interviewer" ? [{ key: "skill_area", label: "Skill area" }] : []),
          ...(person ? [{ key: "user_id", label: "Portal user", value: (m) => userName(m.user_id) || (m.user_id ? "Linked" : "—") }] : []),
          { key: "active", label: "Active", render: (m) => <Switch checked={m.active} onCheckedChange={() => toggle(m)} data-testid={`master-active-${m.name}`} /> },
          { key: "edit", label: "", sortable: false, render: (m) => <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => setEdit(m)} data-testid={`master-edit-${m.name}`}><Pencil className="h-3.5 w-3.5" /></Button> }]} />
      <FormDialog open={!!edit} onOpenChange={(o) => !o && setEdit(null)} title={`${edit?.id ? "Edit" : "Add"} · ${meta.master_types[type]}`} fields={fields} initial={edit} onSubmit={save} testid="master-form" />
    </div>
  );
}

function Transitions() {
  const { meta, reloadRef } = useAuth();
  const all = [...meta.pipeline, ...meta.terminal];
  const [t, setT] = useState(meta.settings.transitions || {});
  const [busy, setBusy] = useState(false);
  const flip = (from, to) => setT((x) => ({ ...x, [from]: (x[from] || []).includes(to) ? x[from].filter((s) => s !== to) : [...(x[from] || []), to] }));
  const save = async () => { setBusy(true); try { const { data } = await api.put("/settings", { transitions: t }); setT(data.transitions || {}); toast.success("Transitions saved"); reloadRef(); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); } };
  return (
    <Section title="Permitted status transitions" actions={<Button size="sm" onClick={save} disabled={busy} data-testid="transitions-save">{busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Save</Button>}>
      <p className="mb-3 text-xs text-subtle">Rows = current stage, columns = target stage. Only paths in the defined workflow can be switched on (greyed boxes are never allowed); you can switch paths off.
        Forward moves still need every earlier stage's record — the stage wizard collects them. Joined and closed outcomes cannot be reopened.</p>
      <div className="scroll-thin overflow-auto"><table className="text-[11px]" data-testid="transitions-matrix"><thead><tr><th className="sticky left-0 bg-white p-1 text-left">From \ To</th>{all.map((s) => <th key={s} className="h-28 p-1 align-bottom font-medium"><span className="block w-4 rotate-180 whitespace-nowrap [writing-mode:vertical-rl]">{s}</span></th>)}</tr></thead>
        <tbody>{all.map((from) => <tr key={from} className="border-t border-[#EEF1F5]"><td className="sticky left-0 whitespace-nowrap bg-white p-1 pr-3 font-medium">{from}</td>
          {all.map((to) => <td key={to} className="p-1 text-center">{from === to || !(meta.workflow_matrix?.[from] || []).includes(to) ? <span className="text-zinc-200">·</span> : <Checkbox checked={(t[from] || []).includes(to)} onCheckedChange={() => flip(from, to)} data-testid={`tr-${from}-${to}`.toLowerCase().replace(/ /g, "-")} />}</td>)}</tr>)}</tbody></table></div>
    </Section>
  );
}

function General() {
  const { meta, reloadRef } = useAuth();
  const [v, setV] = useState({});
  useEffect(() => { setV({ rating_scale: String(meta.settings.rating_scale || 5), stale_days: meta.settings.stale_days, offer_expiry_alert_days: meta.settings.offer_expiry_alert_days, management_view_all_interviews: !!meta.settings.management_view_all_interviews }); }, [meta]);
  const save = async () => { try { await api.put("/settings", { rating_scale: Number(v.rating_scale), stale_days: Number(v.stale_days), offer_expiry_alert_days: Number(v.offer_expiry_alert_days), management_view_all_interviews: !!v.management_view_all_interviews }); toast.success("Settings saved"); reloadRef(); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Section title="Workflow settings">
        <div className="space-y-4">
          <div className="space-y-1"><Label className="text-xs">Interview rating scale</Label><SelectField value={v.rating_scale} onChange={(x) => setV({ ...v, rating_scale: x })} allowNone={false} options={["3", "4", "5", "10"].map((s) => ({ value: s, label: `1 – ${s}` }))} testid="setting-rating-scale" /></div>
          <div className="space-y-1"><Label className="text-xs">Flag candidates stuck in a stage after (days)</Label><Input type="number" value={v.stale_days ?? ""} onChange={(e) => setV({ ...v, stale_days: e.target.value })} data-testid="setting-stale-days" /></div>
          <div className="space-y-1"><Label className="text-xs">Alert before offer expiry (days)</Label><Input type="number" value={v.offer_expiry_alert_days ?? ""} onChange={(e) => setV({ ...v, offer_expiry_alert_days: e.target.value })} data-testid="setting-expiry-days" /></div>
          <label className="flex items-start gap-3 text-sm"><Switch checked={!!v.management_view_all_interviews} onCheckedChange={(x) => setV({ ...v, management_view_all_interviews: x })} data-testid="setting-mgmt-all-interviews" />
            <span>Management can view all interviews<span className="block text-xs text-subtle">Off: Management members see only the interviews they are assigned to (their dashboards still show organisation-wide counts). They can never change interviews they are not assigned to.</span></span></label>
          <Button onClick={save} data-testid="settings-save">Save settings</Button>
        </div>
      </Section>
      <Section title="System statuses">
        <p className="mb-3 text-xs text-subtle">Status values drive workflow automation and analytics, so they are fixed. Control which candidate stage moves are allowed in the Transitions tab.</p>
        {[["Candidate (pipeline)", meta.pipeline], ["Candidate (alternate)", meta.terminal], ["Requisition", meta.req_statuses], ["Interview", meta.interview_statuses], ["Offer", meta.offer_statuses], ["Joining", meta.joining_statuses]].map(([l, arr]) => (
          <div key={l} className="mb-3"><p className="eyebrow mb-1.5">{l}</p><div className="flex flex-wrap gap-1.5">{arr.map((s) => <StatusBadge key={s} status={s} />)}</div></div>))}
      </Section>
    </div>
  );
}

function StatusMigration() {
  const { data: p, reload, loading } = useFetch("/admin/migrations/joined-to-screening");
  const [confirm, setConfirm] = useState("");
  const [db, setDb] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  if (loading || !p) return <Section title="Status migration: Joined → Screening"><Loader2 className="h-4 w-4 animate-spin text-[#9AA2AE]" /></Section>;
  const run = async () => {
    setBusy(true);
    try { const { data } = await api.post("/admin/migrations/joined-to-screening", { confirm, database: db, expected_count: p.count }); setResult(data); setConfirm(""); setDb(""); reload(); toast.success(data.already_applied ? "Already applied — nothing changed" : `${data.changed} application(s) moved to Screening`); }
    catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <Section title="Status migration: Joined → Screening" testid="status-migration">
      <div className="space-y-3 text-sm">
        <p className="text-xs text-subtle">One-time change of the <b>current stage</b> of every application now in Joined to Screening ({p.reason}). Candidates, offers, joining records and dates, interview feedback, CTC and fees, and history are kept. The affected applications are backed up first; the run is verified and can be rolled back from the backup with the migration script.</p>
        <div className="grid gap-2 sm:grid-cols-4 text-xs">
          <div><p className="eyebrow">Environment</p><p data-testid="mig-env">{p.environment}</p></div>
          <div><p className="eyebrow">Database</p><p className="font-mono">{p.database}</p></div>
          <div><p className="eyebrow">Host</p><p className="font-mono">{p.mongo_host}</p></div>
          <div><p className="eyebrow">Applications in total</p><p>{p.total_applications}</p></div>
        </div>
        {p.already_applied ? (
          <p className="flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800" data-testid="mig-done"><CheckCircle2 className="h-4 w-4" />Completed on {p.last_run?.completed_at?.slice(0, 16).replace("T", " ")} — {p.last_run?.changed} application(s) moved. Running it again changes nothing.</p>
        ) : (
          <>
            <p className="font-semibold" data-testid="mig-count">{p.count} application(s) are currently Joined and would move to Screening.</p>
            {p.closed_requisitions_affected.length > 0 && <p className="text-xs text-amber-800">Some belong to closed / filled requisitions ({p.closed_requisitions_affected.join(", ")}); requisition status is not changed.</p>}
            {p.count > 0 && <DataTable testid="mig-table" data={p.applications} pageSize={6} columns={[{ key: "application_code", label: "Application" }, { key: "candidate", label: "Candidate" },
              { key: "requisition_code", label: "Requisition" }, { key: "actual_join_date", label: "Joined on" }, { key: "has_cost", label: "Cost on record", render: (r) => (r.has_cost ? "Yes" : "No") }]} />}
            {p.count > 0 && (
              <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
                <div className="space-y-1"><Label className="text-xs">Type <b>{p.confirm_phrase}</b></Label><Input value={confirm} onChange={(e) => setConfirm(e.target.value)} data-testid="mig-confirm" /></div>
                <div className="space-y-1"><Label className="text-xs">Type the database name <b>{p.database}</b></Label><Input value={db} onChange={(e) => setDb(e.target.value)} data-testid="mig-db" /></div>
                <Button variant="destructive" disabled={busy || confirm !== p.confirm_phrase || db !== p.database} onClick={run} data-testid="mig-run">{busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Move {p.count} to Screening</Button>
              </div>
            )}
          </>
        )}
        {result?.verification && (
          <div className="rounded-md border border-line p-3 text-xs" data-testid="mig-result">
            <p className="font-semibold">{result.ok ? "Verified" : "Needs review"} — {result.changed} moved · backup {result.backup_id}</p>
            <p>All targets in Screening: {String(result.verification.all_moved)} · application count unchanged: {String(result.verification.application_count_unchanged)} · other applications untouched: {String(result.verification.other_applications_untouched)} · transactional: {String(result.verification.transactional)}</p>
            <p>Related records kept: {Object.entries(result.verification.related_records_kept).map(([k, v]) => `${k} ${v}`).join(", ")} · cost records kept: {result.verification.hire_costs_kept}</p>
          </div>
        )}
      </div>
    </Section>
  );
}

function DataCleanup() {
  const { data: st, reload } = useFetch("/admin/data-status");
  const [phrase, setPhrase] = useState("");
  const [dbName, setDbName] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  if (!st) return <p className="text-sm text-[#9AA2AE]">Loading…</p>;
  const total = Object.entries(st.counts).reduce((a, [, v]) => a + v, 0);
  const ok = phrase.trim() === st.confirm_phrase && dbName.trim() === st.database;
  const prod = /prod/i.test(st.environment);
  const run = async () => {
    setBusy(true);
    try { const r = await api.post("/admin/cleanup", { confirm: phrase.trim(), database: dbName.trim() }); setDone(r.data); setPhrase(""); setDbName(""); reload(); toast.success("Recruitment data deleted"); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const label = (k) => st.labels[k] || { test_users: "Test user accounts (TEST_ / @mms.test)", test_master_entries: "Test master entries (TEST_)", master_links_cleared: "Master entries unlinked from deleted users" }[k] || k;
  return (
    <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
      <Section title="Delete test / demo recruitment data" testid="cleanup-section">
        <div className={cn("mb-4 flex items-start gap-3 rounded-lg border p-3 text-sm", prod ? "border-rose-300 bg-rose-50 text-rose-900" : "border-amber-200 bg-amber-50 text-amber-900")} data-testid="cleanup-target">
          <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0" />
          <div><p className="font-semibold">Target: {st.environment.toUpperCase()} environment · database <span className="font-mono">{st.database}</span></p>
            <p className="text-xs">Host {st.mongo_host}. This permanently deletes every record listed here from the connected database. It cannot be undone — take a backup first if in doubt.</p></div>
        </div>
        <table className="w-full text-sm" data-testid="cleanup-counts"><tbody>
          {Object.entries(st.counts).map(([k, v]) => <tr key={k} className="border-b border-[#EEF1F5] last:border-0"><td className="py-1.5 text-[#4B5361]">{label(k)}</td><td className="py-1.5 text-right font-mono">{v}</td></tr>)}
          <tr><td className="pt-2 font-semibold">Total records to delete</td><td className="pt-2 text-right font-mono font-semibold">{total}</td></tr>
        </tbody></table>
        <div className="mt-5 space-y-3">
          <div className="space-y-1"><Label className="text-xs">Type <span className="font-mono font-semibold">{st.confirm_phrase}</span></Label><Input value={phrase} onChange={(e) => setPhrase(e.target.value)} data-testid="cleanup-phrase" /></div>
          <div className="space-y-1"><Label className="text-xs">Type the database name <span className="font-mono font-semibold">{st.database}</span></Label><Input value={dbName} onChange={(e) => setDbName(e.target.value)} data-testid="cleanup-db" /></div>
          <Button variant="destructive" disabled={!ok || busy || total === 0} onClick={run} data-testid="cleanup-run">{busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Trash2 className="mr-2 h-4 w-4" />}Delete {total} records</Button>
        </div>
      </Section>
      <div className="space-y-4">
        <Section title="Preserved">
          <ul className="space-y-1.5 text-sm text-[#4B5361]">
            <li>{st.preserved.users} user account(s), including the Super Admin</li>
            <li>{st.preserved.masters} master data entries (departments, recruiters, sources…)</li>
            <li>{st.preserved.settings} settings document(s), roles & permissions, workflow transitions</li>
            <li>Excel import templates, database schema and indexes</li>
          </ul>
          {st.masters_created_by_import > 0 && <p className="mt-3 text-xs text-amber-700">{st.masters_created_by_import} master entries were created by earlier Excel imports. They are kept — review them under Master data if they came from test files.</p>}
          <p className="mt-3 text-xs text-[#9AA2AE]">Nothing is re-seeded after cleanup. Uploaded CV / offer-letter file records are removed; the stored objects themselves stay in file storage.</p>
        </Section>
        {done && <Section title="Cleanup summary" testid="cleanup-summary">
          <p className={cn("mb-3 flex items-center gap-2 text-sm font-semibold", done.verified ? "text-emerald-700" : "text-rose-700")}><CheckCircle2 className="h-4 w-4" />{done.verified ? `Verified: ${done.total_deleted} records deleted, all recruitment tables are empty.` : "Some records remain — see below."}</p>
          <table className="w-full text-sm"><tbody>{Object.entries(done.deleted).map(([k, v]) => <tr key={k} className="border-b border-[#EEF1F5] last:border-0"><td className="py-1 text-[#4B5361]">{label(k)}</td><td className="py-1 text-right font-mono">{v}</td></tr>)}</tbody></table>
        </Section>}
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const { can } = useAuth();
  return (
    <div>
      <PageHeader eyebrow="Administration" title="Master Data & Settings" description="Maintain the lists used across the portal. Deactivated entries stay on historical records." />
      <Tabs defaultValue="masters">
        <TabsList><TabsTrigger value="masters" data-testid="settings-tab-masters">Master data</TabsTrigger>{can("settings.manage") && <><TabsTrigger value="transitions" data-testid="settings-tab-transitions">Transitions</TabsTrigger><TabsTrigger value="general" data-testid="settings-tab-general">General</TabsTrigger></>}{can("users.super") && <TabsTrigger value="cleanup" data-testid="settings-tab-cleanup">Data cleanup</TabsTrigger>}</TabsList>
        <TabsContent value="masters"><Masters /></TabsContent>
        <TabsContent value="transitions"><Transitions /></TabsContent>
        <TabsContent value="general"><General /></TabsContent>
        {can("users.super") && <TabsContent value="cleanup" className="space-y-4"><StatusMigration /><DataCleanup /></TabsContent>}
      </Tabs>
    </div>
  );
}
