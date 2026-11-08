import { useState } from "react";
import { AlertTriangle, CheckCircle2, Download, FileSpreadsheet, Loader2, Upload, ListChecks } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useAuth } from "@/context/AuthContext";
import { Kpi, PageHeader, Section } from "@/components/common/Page";
import { DataTable } from "@/components/common/DataTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { SelectField } from "@/components/common/FormDialog";
import { useFetch } from "@/lib/useFetch";
import { api, download, errMsg, fmtDateTime } from "@/lib/api";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

const TYPES = [
  { value: "requisitions", label: "Recruitment Requisitions" },
  { value: "candidates", label: "Candidate Master" },
  { value: "applications", label: "Candidate-Requisition Mapping" },
  { value: "interviews", label: "Interview Details" },
  { value: "costs", label: "Recruitment Partners & Costs" },
  { value: "interviewers", label: "Interviewers (legacy sheet: column per skill area)" },
];
const ORDER = ["requisitions", "candidates", "applications", "interviews", "costs"];
const STEPS = ["Upload", "Preview & map", "Validate", "Summary"];
const STATUS_LABEL = { valid: "Ready", update: "Will update", duplicate: "Duplicate", error: "Error", sample: "Sample row" };

function recordLabel(type, d) {
  if (type === "applications" || type === "interviews") return [d.candidate_ref, d.requisition_code].filter(Boolean).join(" → ");
  if (type === "costs") return d.partner || d.invoice_no || d.category;
  return d.name || d.title || d.code;
}
function recordDetails(type, d) {
  const bits = {
    requisitions: [d.code, d.department, d.positions != null && `${d.positions} positions`, d.crf_date && `CRF ${d.crf_date}`, d.status],
    candidates: [d.code, d.email, d.phone, d.source, d.recruiter],
    applications: [d.status, d.actual_join_date && `DOJ ${d.actual_join_date}`, d.recruiter],
    interviews: [d.round_number && `Round ${d.round_number}`, d.round_type, d.date, d.status, d.outcome],
    costs: [d.category, d.invoice_no, d.amount != null && `₹${d.amount} L`, d.payment_status],
    interviewers: [d.skill_area],
  }[type] || [];
  return bits.filter(Boolean).join(" · ");
}

function Templates() {
  const { data } = useFetch("/import/templates");
  const [busy, setBusy] = useState(null);
  const get = async (k) => { setBusy(k); try { await download(`/import/templates/${k}`); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(null); } };
  const sorted = (data || []).slice().sort((a, b) => ORDER.indexOf(a.key) - ORDER.indexOf(b.key));
  return (
    <Section title="Step 1 — Download a template" testid="import-templates">
      <p className="mb-4 text-xs text-subtle">Each workbook has an <b>Instructions</b> sheet, dropdowns from your master data, date checks (DD-MM-YYYY) and a yellow sample row that is never imported. Black headers marked * are mandatory. Import in the order shown so later templates can refer to earlier records.</p>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {sorted.map((t, i) => (
          <div key={t.key} className="flex flex-col justify-between rounded-lg border border-line p-3" data-testid={`template-${t.key}`}>
            <div>
              <p className="eyebrow">Template {i + 1}</p>
              <p className="mt-1 text-sm font-semibold text-ink">{t.title}</p>
              <p className="mt-1 text-[11px] text-subtle">{t.columns.length} columns · {t.columns.filter((c) => c.required).length} mandatory</p>
            </div>
            <Button size="sm" variant="outline" className="mt-3" disabled={busy === t.key} onClick={() => get(t.key)} data-testid={`template-download-${t.key}`}>
              {busy === t.key ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Download className="mr-1.5 h-3.5 w-3.5" />}Download .xlsx
            </Button>
          </div>
        ))}
      </div>
    </Section>
  );
}

export default function ImportPage() {
  const { reloadRef } = useAuth();
  const [step, setStep] = useState(0);
  const [batch, setBatch] = useState(null);
  const [sheet, setSheet] = useState(null);
  const [type, setType] = useState(null);
  const [mapping, setMapping] = useState({});
  const [showMap, setShowMap] = useState(false);
  const [opts, setOpts] = useState({ skip_duplicates: true, create_missing_roles: false, create_missing_masters: false, update_existing: false });
  const [val, setVal] = useState(null);
  const [res, setRes] = useState(null);
  const [skipErrors, setSkipErrors] = useState(false);
  const [busy, setBusy] = useState(false);
  const [show, setShow] = useState("all");
  const { data: hist, reload: reloadHist } = useFetch("/import/history");
  const sh = batch?.sheets.find((s) => s.name === sheet);
  const legacy = sh && !sh.template;

  const upload = async (file) => {
    if (!file) return;
    setBusy(true);
    const fd = new FormData(); fd.append("file", file);
    try {
      const r = await api.post("/import/upload", fd);
      setBatch(r.data);
      const first = r.data.sheets.find((s) => s.template) || r.data.sheets.find((s) => s.suggested_type) || r.data.sheets[0];
      pick(first); setStep(1);
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const pick = (s) => { setSheet(s?.name); setType(s?.suggested_type || null); setMapping(s?.suggested_mapping || {}); setShowMap(!s?.template); setVal(null); };
  const setOpt = (k, v) => { setOpts({ ...opts, [k]: v }); setVal(null); };
  const body = () => ({ batch_id: batch.id, sheet, type, mapping: Object.fromEntries(Object.entries(mapping).filter(([, v]) => v)), ...opts });
  const validate = async () => {
    setBusy(true);
    try { const r = await api.post("/import/validate", body()); setVal(r.data); setSkipErrors(false); setShow("all"); setStep(2); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const commit = async () => {
    setBusy(true);
    try { const r = await api.post("/import/commit", body()); setRes(r.data); setStep(3); reloadRef(); reloadHist(); toast.success("Import completed"); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const reset = () => { setStep(0); setBatch(null); setVal(null); setRes(null); };
  const rows = (val?.rows || []).filter((r) => show === "all" || r.status === show || (show === "warn" && r.messages.length && r.status !== "sample"));
  const s = val?.summary;
  const importable = s ? s.valid + s.update + (type === "candidates" && !opts.skip_duplicates ? s.duplicate : 0) : 0;
  const canCommit = s && importable > 0 && (s.error === 0 || skipErrors);

  return (
    <div>
      <PageHeader eyebrow="HR Admin" title="Data Import & Migration" description="Download a standard template, fill it offline, then upload it here. You see a preview and row-level errors before anything is saved, and existing records are never overwritten unless you choose to." />
      <div className="space-y-6">
        {step === 0 && <Templates />}

        <div>
          <div className="mb-4 flex flex-wrap gap-2">{STEPS.map((x, i) => <span key={x} className={cn("rounded-full border px-3 py-1 text-xs font-semibold", i === step ? "border-brand-deep bg-brand-deep text-white" : i < step ? "border-[#D5DBE3] bg-white text-[#3A414C]" : "border-line text-[#9AA2AE]")}>{i + 1}. {x}</span>)}</div>

          {step === 0 && (
            <label className="flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed border-[#D5DBE3] bg-white py-14 hover:border-zinc-500" data-testid="import-dropzone">
              {busy ? <Loader2 className="h-8 w-8 animate-spin text-[#9AA2AE]" /> : <FileSpreadsheet className="h-10 w-10 text-[#9AA2AE]" strokeWidth={1.4} />}
              <p className="text-sm font-semibold">Step 2 — Upload the completed .xlsx file</p><p className="text-xs text-subtle">Portal templates are recognised automatically. Older MMS workbooks can still be mapped column by column.</p>
              <input type="file" accept=".xlsx,.xlsm" hidden onChange={(e) => { upload(e.target.files[0]); e.target.value = ""; }} data-testid="import-file-input" />
            </label>
          )}

          {step === 1 && batch && (
            <div className="space-y-4">
              <Section title={`${batch.filename} — preview`}>
                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="space-y-1"><Label className="text-xs">Sheet</Label><SelectField value={sheet} onChange={(v) => pick(batch.sheets.find((x) => x.name === v))} allowNone={false} options={batch.sheets.map((x) => ({ value: x.name, label: `${x.name} (${x.row_count} rows)` }))} testid="import-sheet" /></div>
                  <div className="space-y-1 sm:col-span-2"><Label className="text-xs">Import as</Label><SelectField value={type} onChange={(v) => { setType(v); setMapping(v === sh?.template ? sh.suggested_mapping : {}); setVal(null); }} options={TYPES} placeholder="Choose import type" testid="import-type" /></div>
                </div>
                {sh?.template && <p className="mt-3 flex items-center gap-2 text-xs text-emerald-700" data-testid="import-template-detected"><CheckCircle2 className="h-4 w-4" />Recognised as the {TYPES.find((t) => t.value === sh.template)?.label} template — columns are mapped automatically.</p>}
                {sh && <div className="scroll-thin mt-4 overflow-x-auto rounded-lg border" data-testid="import-preview"><table className="text-xs"><thead><tr className="bg-canvas"><th className="px-3 py-2 text-left font-semibold text-[#9AA2AE]">Row</th>{sh.headers.map((h) => <th key={h} className="whitespace-nowrap px-3 py-2 text-left font-semibold">{h}</th>)}</tr></thead>
                  <tbody>{sh.preview.map((r, i) => <tr key={i} className={cn("border-t", r.some((c) => String(c ?? "").includes("[SAMPLE]")) && "bg-amber-50 text-amber-800")}><td className="px-3 py-1.5 text-[#9AA2AE]">{sh.header_row + i + 2}</td>{r.map((c, k) => <td key={k} className="whitespace-nowrap px-3 py-1.5 text-[#4B5361]">{c === null ? "" : String(c)}</td>)}</tr>)}</tbody></table></div>}
                {sh && <p className="mt-2 text-[11px] text-[#9AA2AE]">Showing the first {sh.preview.length} of {sh.row_count} rows.</p>}
              </Section>

              {type && type !== "interviewers" && (
                <Section title="Options" testid="import-options">
                  <div className="flex flex-col gap-3">
                    <label className="flex items-start gap-2 text-sm"><Switch checked={opts.update_existing} onCheckedChange={(c) => setOpt("update_existing", c)} data-testid="import-update-existing" /><span><b>Update existing records (overwrite)</b><span className="block text-xs text-subtle">Off by default. When off, rows that match an existing record (same ID, email or mobile) are skipped as duplicates. When on, the filled-in columns replace the values in the portal.</span></span></label>
                    <label className="flex items-start gap-2 text-sm"><Switch checked={opts.create_missing_masters} onCheckedChange={(c) => setOpt("create_missing_masters", c)} data-testid="import-create-masters" /><span><b>Add unknown values to master data</b><span className="block text-xs text-subtle">Off by default. When off, a department, recruiter, role or partner that is not in Master Data is reported as an error.</span></span></label>
                    {type === "candidates" && legacy && <label className="flex items-center gap-2 text-sm"><Switch checked={opts.create_missing_roles} onCheckedChange={(c) => setOpt("create_missing_roles", c)} data-testid="import-create-roles" />Create requisitions for unmatched roles (legacy workbook)</label>}
                    {type === "candidates" && legacy && <label className="flex items-center gap-2 text-sm"><Switch checked={!opts.skip_duplicates} onCheckedChange={(c) => setOpt("skip_duplicates", !c)} data-testid="import-link-duplicates" />Link duplicates to existing candidates (adds new applications)</label>}
                  </div>
                  {opts.update_existing && <p className="mt-3 flex items-center gap-2 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800"><AlertTriangle className="h-4 w-4" />Matching records will be overwritten with the values in this file.</p>}
                </Section>
              )}

              {type && type !== "interviewers" && (
                <Section title="Column mapping" testid="import-mapping" actions={sh?.template && <Button size="sm" variant="ghost" onClick={() => setShowMap(!showMap)} data-testid="import-toggle-mapping">{showMap ? "Hide" : "Review"} mapping</Button>}>
                  {!showMap ? <p className="text-xs text-subtle">{Object.values(mapping).filter(Boolean).length} of {Object.keys(batch.fields[type]).length} fields mapped to the template columns.</p> : (
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                      {Object.entries(batch.fields[type]).map(([k, l]) => (
                        <div key={k} className="space-y-1"><Label className="text-xs">{l}{batch.required[type]?.includes(k) && <span className="text-rose-600"> *</span>}</Label>
                          <SelectField value={mapping[k]} onChange={(v) => { setMapping({ ...mapping, [k]: v }); setVal(null); }} options={sh.headers.map((h) => ({ value: h, label: h }))} placeholder="— not mapped —" testid={`map-${k}`} /></div>))}
                    </div>)}
                </Section>
              )}
              {type === "interviewers" && <p className="text-sm text-subtle">Each column header becomes the interviewer's skill area; every name below it is imported once.</p>}
              <div className="flex gap-2"><Button variant="outline" onClick={reset}>Back</Button><Button disabled={!type || busy} onClick={validate} data-testid="import-validate-btn">{busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ListChecks className="mr-2 h-4 w-4" />}Validate</Button></div>
            </div>
          )}

          {step === 2 && val && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
                <Kpi label="Total rows" value={s.total} testid="import-total-count" />
                <Kpi label="Ready to import" value={s.valid} accent="text-emerald-700" testid="import-valid-count" />
                <Kpi label="Will update" value={s.update} hint={opts.update_existing ? "Overwrite is on" : "Overwrite is off"} testid="import-update-count" />
                <Kpi label="Duplicates" value={s.duplicate} accent="text-amber-700" hint="Skipped" testid="import-dup-count" />
                <Kpi label="Errors" value={s.error} accent="text-rose-700" hint="Not imported" testid="import-error-count" />
                <Kpi label="Sample rows" value={s.sample} hint="Always ignored" testid="import-sample-count" />
              </div>
              <DataTable testid="import-rows" data={rows} pageSize={15}
                rowClass={(r) => r.status === "error" ? "bg-rose-50/50" : r.status === "duplicate" ? "bg-amber-50/40" : undefined}
                toolbar={<SelectField value={show} onChange={(v) => setShow(v || "all")} allowNone={false} options={[{ value: "all", label: "All rows" }, { value: "error", label: "Errors" }, { value: "duplicate", label: "Duplicates" }, { value: "valid", label: "Ready" }, { value: "update", label: "Will update" }, { value: "sample", label: "Sample rows" }, { value: "warn", label: "With messages" }]} testid="import-row-filter" className="w-40" />}
                columns={[{ key: "row", label: "Excel row" }, { key: "status", label: "Result", value: (r) => STATUS_LABEL[r.status], render: (r) => <StatusBadge status={STATUS_LABEL[r.status]} tone={{ valid: "green", update: "plum", duplicate: "amber", error: "rose", sample: "zinc" }[r.status]} /> },
                  { key: "name", label: "Record", value: (r) => recordLabel(type, r.data) },
                  { key: "extra", label: "Details", value: (r) => recordDetails(type, r.data), className: "text-xs text-subtle" },
                  { key: "cols", label: "Columns with errors", value: (r) => (r.error_columns || []).map((c) => c.replace(/[*†]$/, "")).join(", "), className: "text-xs font-medium text-rose-700" },
                  { key: "messages", label: "Messages", value: (r) => r.messages.join("; "), className: "text-xs text-[#3A414C]" }]} />
              {s.error > 0 && (
                <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800" data-testid="import-error-note">
                  <p className="font-semibold">{s.error} row(s) have errors and will not be imported.</p>
                  <p className="text-xs">Download the error report, correct the rows in your Excel file and upload it again — or import only the valid rows now.</p>
                  <label className="mt-2 flex items-center gap-2 text-xs"><Checkbox checked={skipErrors} onCheckedChange={(c) => setSkipErrors(!!c)} data-testid="import-skip-errors" />Import the {importable} valid row(s) and skip the {s.error} error row(s)</label>
                </div>)}
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" onClick={() => setStep(1)}>Back</Button>
                {val.report_rows > 0 && <Button variant="outline" onClick={() => download(`/import/${batch.id}/rejected`).catch((e) => toast.error(errMsg(e)))} data-testid="import-download-errors"><Download className="mr-2 h-4 w-4" />Download error report ({val.report_rows} rows)</Button>}
                <Button disabled={busy || !canCommit} onClick={commit} data-testid="import-commit-btn">{busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}<Upload className="mr-2 h-4 w-4" />Confirm import of {importable} row(s)</Button>
              </div>
              <p className="text-xs text-subtle">The file is validated again when you confirm. If anything fails while saving, the whole import is rolled back.</p>
            </div>
          )}

          {step === 3 && res && (
            <Section testid="import-summary">
              <div className="flex items-center gap-3"><CheckCircle2 className="h-6 w-6 text-emerald-600" /><p className="text-lg font-semibold">Import complete</p></div>
              <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
                <Kpi label="Total rows" value={res.total} testid="import-result-total" />
                <Kpi label="Successfully imported" value={res.imported + res.updated + (res.linked || 0)} accent="text-emerald-700" hint={`${res.imported} new · ${res.updated} updated${res.linked ? ` · ${res.linked} linked` : ""}`} testid="import-result-imported" />
                <Kpi label="Skipped" value={res.skipped} hint={`incl. ${res.samples} sample row(s)`} testid="import-result-skipped" />
                <Kpi label="Duplicate records" value={res.duplicates} accent="text-amber-700" testid="import-result-duplicates" />
                <Kpi label="Failed records" value={res.failed} accent="text-rose-700" testid="import-result-failed" />
              </div>
              {res.applications > 0 && <p className="mt-3 text-xs text-subtle">{res.applications} application(s) were created from the legacy role column.</p>}
              <div className="mt-4 flex flex-wrap gap-2">
                {res.rejected_count > 0 && <Button variant="outline" onClick={() => download(`/import/${batch.id}/rejected`)} data-testid="import-download-rejected"><Download className="mr-2 h-4 w-4" />Download {res.rejected_count} rejected rows</Button>}
                <Button variant="outline" onClick={() => { setStep(1); setVal(null); setRes(null); }} data-testid="import-another-sheet">Import another sheet</Button>
                <Button onClick={reset} data-testid="import-new-file">Upload another file</Button>
              </div>
            </Section>
          )}
        </div>

        {hist?.length > 0 && <div><p className="eyebrow mb-2">Import history</p>
          <DataTable testid="import-history" data={hist} pageSize={5} columns={[{ key: "filename", label: "File" }, { key: "type", label: "Type", value: (h) => TYPES.find((t) => t.value === h.type)?.label || h.type }, { key: "uploaded_by", label: "By" }, { key: "committed_at", label: "Imported", render: (h) => fmtDateTime(h.committed_at) },
            { key: "result", label: "Result", value: (h) => { const r = h.result || {}; return `${r.total ?? "—"} rows: ${(r.imported || 0) + (r.updated || 0) + (r.linked || 0)} imported, ${r.skipped || 0} skipped, ${r.duplicates || 0} duplicates, ${r.failed || 0} failed`; } },
            { key: "dl", label: "", sortable: false, render: (h) => <Button size="sm" variant="ghost" onClick={() => download(`/import/${h.id}/rejected`).catch(() => toast.info("No rejected rows"))}>Rejected rows</Button> }]} /></div>}
      </div>
    </div>
  );
}
