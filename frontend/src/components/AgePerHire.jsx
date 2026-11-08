import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowDownRight, ArrowUpRight, Download, Minus } from "lucide-react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";
import { Kpi, Section } from "@/components/common/Page";
import { DataTable, EmptyState } from "@/components/common/DataTable";
import { SelectField } from "@/components/common/FormDialog";
import { download, fmtDate } from "@/lib/api";
import { cn } from "@/lib/utils";

const axis = { fontSize: 11, fill: "#71717A" };
const d = (v) => (v === null || v === undefined ? "N/A" : `${v} d`);

export const APH_FORMULA = "Age per Hire = Actual Date of Joining − CRF Raised Date (calendar days). Only candidates who have joined are counted.";

/** Filters for Age per Hire: department, role, recruiter, source, joining-date range. */
export function AphFilters({ f, setF, testid = "aph-filters" }) {
  const { list } = useAuth();
  const m = (t) => list(t).map((x) => ({ value: x.id, label: x.name }));
  const roles = list("job_title").map((x) => ({ value: x.name, label: x.name }));
  const sel = (k, opts, ph) => <SelectField value={f[k]} onChange={(v) => setF({ ...f, [k]: v })} options={opts} placeholder={ph} testid={`${testid}-${k}`} className="w-40" />;
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid={testid}>
      {sel("department_id", m("department"), "All departments")}
      {roles.length ? sel("role_exact", roles, "All roles") : <Input className="h-9 w-36" placeholder="Role contains…" value={f.role || ""} onChange={(e) => setF({ ...f, role: e.target.value })} data-testid={`${testid}-role`} />}
      {sel("recruiter_id", m("recruiter"), "All recruiters")}
      {sel("source_id", m("source"), "All sources")}
      <span className="text-[11px] text-zinc-400">Joined</span>
      <input type="date" className="h-9 rounded-md border px-2 text-xs" value={f.date_from || ""} onChange={(e) => setF({ ...f, date_from: e.target.value })} data-testid={`${testid}-from`} />
      <span className="text-xs text-zinc-400">to</span>
      <input type="date" className="h-9 rounded-md border px-2 text-xs" value={f.date_to || ""} onChange={(e) => setF({ ...f, date_to: e.target.value })} data-testid={`${testid}-to`} />
      {Object.values(f).some(Boolean) && <Button variant="ghost" size="sm" onClick={() => setF({})} data-testid={`${testid}-clear`}>Clear</Button>}
    </div>
  );
}

function Change({ c, label }) {
  if (!c) return null;
  const none = c.change === null || c.change === undefined;
  const Icon = none ? Minus : c.change > 0 ? ArrowUpRight : c.change < 0 ? ArrowDownRight : Minus;
  // more days = slower hiring = worse
  const tone = none || c.change === 0 ? "text-zinc-500" : c.change > 0 ? "text-rose-700" : "text-emerald-700";
  return (
    <div className="text-xs">
      <p className="text-zinc-500">{label} <span className="text-zinc-400">· {c.period}</span></p>
      <p className={cn("flex items-center gap-1 font-semibold", tone)}>
        <Icon className="h-3.5 w-3.5 shrink-0" />
        {none ? (c.avg === null ? "No hires yet this period" : "No hires in previous period") : `${c.change > 0 ? "+" : ""}${c.change} d`}
        {c.avg !== null && !none && <span className="font-normal text-zinc-400">({c.avg} d vs {c.previous_avg} d)</span>}
      </p>
    </div>
  );
}

export function AphTrend({ aph, height = 220 }) {
  const [mode, setMode] = useState("monthly");
  const data = aph[mode];
  return (
    <div>
      <div className="mb-2 flex justify-end gap-1">
        {["monthly", "quarterly"].map((m) => <Button key={m} size="sm" variant={mode === m ? "default" : "ghost"} className="h-7 text-xs capitalize" onClick={() => setMode(m)} data-testid={`aph-trend-${m}`}>{m}</Button>)}
      </div>
      {!data.length ? <EmptyState title="No completed hires yet" hint="The trend appears once joined candidates have an actual joining date and their requisition has a CRF Raised Date." /> : (
        <ResponsiveContainer width="100%" height={height}>
          <LineChart data={data} margin={{ left: 0, right: 8 }}>
            <CartesianGrid stroke="#F4F4F5" /><XAxis dataKey="period" tick={axis} /><YAxis tick={axis} allowDecimals={false} unit=" d" width={48} />
            <Tooltip formatter={(v, n) => [`${v} days`, n === "avg" ? "Average" : "Median"]} labelFormatter={(l) => `${l}`} />
            <Line dataKey="avg" name="avg" stroke="#18181B" strokeWidth={2} dot />
            <Line dataKey="median" name="median" stroke="#D97706" strokeWidth={1.5} strokeDasharray="4 3" dot={false} />
          </LineChart>
        </ResponsiveContainer>)}
      <p className="mt-1 text-[11px] text-zinc-400"><span className="font-semibold text-zinc-700">—</span> average · <span className="font-semibold text-amber-600">- -</span> median, by month / quarter of joining</p>
    </div>
  );
}

/** Executive KPI card + current hiring age + data-quality flags. */
export function AphKpis({ aph }) {
  const c = aph.completed;
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      <div className="rounded-xl border border-[#18181B] bg-white p-4" data-testid="kpi-age-per-hire">
        <p className="eyebrow">Age per Hire (avg)</p>
        <p className="mt-2 text-3xl font-extrabold tracking-tight text-zinc-900">{c.avg === null ? "N/A" : <>{c.avg}<span className="ml-1 text-base font-semibold text-zinc-500">days</span></>}</p>
        <p className="mt-1 text-[11px] text-zinc-400">Median {d(c.median)} · Min {d(c.min)} · Max {d(c.max)} · {c.count} hire{c.count === 1 ? "" : "s"}</p>
        <div className="mt-3 space-y-1 border-t border-zinc-100 pt-2">
          <Change c={aph.month_compare} label="vs previous month" />
          <Change c={aph.quarter_compare} label="vs previous quarter" />
        </div>
      </div>
      <Kpi label="Current hiring age (open reqs)" value={d(aph.current_hiring_age.avg)} hint={`Today − CRF Raised Date · ${aph.current_hiring_age.count} open requisition(s), oldest ${d(aph.current_hiring_age.max)}`} testid="kpi-current-hiring-age" />
      <div className="rounded-xl border border-zinc-200 bg-white p-4" data-testid="kpi-aph-flags">
        <p className="eyebrow">Needs HR data completion</p>
        <p className={cn("mt-2 text-2xl font-extrabold tracking-tight", aph.flagged + aph.current_hiring_age.missing_crf ? "text-amber-700" : "text-zinc-900")}>{aph.flagged + aph.current_hiring_age.missing_crf}</p>
        <p className="mt-1 text-[11px] text-zinc-400">{aph.flagged} joined hire(s) excluded (missing CRF / joining date, or joining before CRF) · {aph.current_hiring_age.missing_crf} open requisition(s) without a CRF Raised Date</p>
      </div>
    </div>
  );
}

const grp = [{ key: "name", label: "Group" }, { key: "count", label: "Hires" }, { key: "avg", label: "Average", render: (r) => d(r.avg) }, { key: "median", label: "Median", render: (r) => d(r.median) }, { key: "min", label: "Min", render: (r) => d(r.min) }, { key: "max", label: "Max", render: (r) => d(r.max) }];

/** Full Age per Hire analysis for the Analytics page. */
export function AphDetail({ aph, f, canExport }) {
  return (
    <div className="space-y-4">
      <AphKpis aph={aph} />
      <p className="text-[11px] text-zinc-500">{APH_FORMULA} The CRF Raised Date is never replaced by another date: records without it are flagged instead.</p>
      <Section title="Age per Hire trend" actions={canExport && <Button size="sm" variant="outline" onClick={() => download("/reports/age-per-hire", f)} data-testid="an-export-age-per-hire"><Download className="mr-1.5 h-3.5 w-3.5" />Export</Button>}><AphTrend aph={aph} height={260} /></Section>
      <div className="grid gap-4 lg:grid-cols-2">
        {[["by_department", "By department"], ["by_role", "By job role"], ["by_recruiter", "By recruiter"], ["by_partner", "By recruitment partner"], ["by_source", "By candidate source"]].map(([k, l]) => (
          <div key={k}><p className="eyebrow mb-2">{l}</p><DataTable testid={`an-aph-${k}`} data={aph[k]} columns={grp} pageSize={6} emptyTitle="No completed hires" /></div>))}
      </div>
      <div><p className="eyebrow mb-2">Hires and their Age per Hire</p>
        <DataTable testid="an-aph-hires" data={aph.hires} pageSize={10} rowClass={(r) => r.flag ? "bg-amber-50/50" : undefined} emptyTitle="No joined candidates in this selection"
          columns={[{ key: "candidate", label: "Candidate" }, { key: "requisition_code", label: "Req" }, { key: "role", label: "Role" }, { key: "department", label: "Department" }, { key: "recruiter", label: "Recruiter" }, { key: "source", label: "Source" },
            { key: "crf_date", label: "CRF raised", render: (r) => fmtDate(r.crf_date) }, { key: "joined_on", label: "Actual DOJ", render: (r) => fmtDate(r.joined_on) }, { key: "days", label: "Age per Hire", render: (r) => d(r.days) },
            { key: "flag", label: "Data flag", className: "text-xs text-amber-800" }]} /></div>
      {aph.incomplete_requisitions?.length > 0 && <div><p className="eyebrow mb-2">Open requisitions missing a CRF Raised Date</p>
        <DataTable testid="an-aph-incomplete" data={aph.incomplete_requisitions} pageSize={6} columns={[{ key: "code", label: "Req", render: (r) => <Link className="underline" to={`/requisitions/${r.id}`}>{r.code}</Link> }, { key: "title", label: "Role" }, { key: "issue", label: "Issue", className: "text-xs text-amber-800" }]} /></div>}
    </div>
  );
}
