import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AphDetail } from "@/components/AgePerHire";
import { Download, SlidersHorizontal } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, Pie, PieChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/context/AuthContext";
import { useFetch } from "@/lib/useFetch";
import { Kpi, PageHeader, Section } from "@/components/common/Page";
import { DataTable, EmptyState } from "@/components/common/DataTable";
import { SelectField } from "@/components/common/FormDialog";
import { COLORS, FunnelChart, KpiGrid, axis } from "@/components/analytics/shared";
import { download, lakhs, num } from "@/lib/api";
import { ChartTip } from "@/components/bento";
import { BRAND, STATUS } from "@/lib/brand";
import { PageLoader } from "@/components/common/Loader";

const n = (v, s = "") => (v === null || v === undefined ? "N/A" : `${v}${s}`);

export function Filters({ f, setF, extra = true }) {
  const { list, meta } = useAuth();
  const { data: reqs } = useFetch("/requisitions");
  const m = (t) => list(t).map((x) => ({ value: x.id, label: x.name }));
  const sel = (k, opts, ph, w = "w-40") => <SelectField value={f[k]} onChange={(v) => setF({ ...f, [k]: v })} options={opts} placeholder={ph} testid={`an-filter-${k}`} className={w} />;
  // advanced filters sit behind "More filters" (all filters remain available); open automatically when one is set
  const advancedKeys = ["partner_id", "source_id", ...(extra ? ["status"] : [])];
  const advancedSet = advancedKeys.filter((k) => f[k]).length;
  const [more, setMore] = useState(advancedSet > 0);
  const active = Object.values(f).filter(Boolean).length;
  return (
    <div className="mb-5 rounded-2xl border border-line bg-white p-3 shadow-[0_1px_2px_rgba(32,36,43,0.04)]" data-testid="analytics-filters">
      <div className="flex flex-wrap items-center gap-2">
        <span className="flex items-center gap-1.5">
          <Input type="date" className="h-9 w-[148px]" value={f.date_from || ""} onChange={(e) => setF({ ...f, date_from: e.target.value })} data-testid="an-filter-from" aria-label="From date" />
          <span className="text-[12px] text-subtle">to</span>
          <Input type="date" className="h-9 w-[148px]" value={f.date_to || ""} onChange={(e) => setF({ ...f, date_to: e.target.value })} data-testid="an-filter-to" aria-label="To date" />
        </span>
        {sel("department_id", m("department"), "All departments")}
        {sel("requisition_id", (reqs || []).map((r) => ({ value: r.id, label: `${r.code} ${r.title}` })), "All requisitions", "w-48")}
        {sel("recruiter_id", m("recruiter"), "All recruiters")}
        <Input className="h-9 w-40" placeholder="Role contains…" value={f.role || ""} onChange={(e) => setF({ ...f, role: e.target.value })} data-testid="an-filter-role" />
        <Button variant={more || advancedSet ? "secondary" : "outline"} onClick={() => setMore(!more)} data-testid="an-filter-more">
          <SlidersHorizontal className="h-4 w-4" />More filters{advancedSet ? ` · ${advancedSet}` : ""}
        </Button>
        {active > 0 && <Button variant="ghost" onClick={() => setF({})} data-testid="an-filter-clear">Clear all</Button>}
      </div>
      {more && (
        <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-line pt-2" data-testid="an-filter-advanced">
          {sel("partner_id", m("partner"), "All partners")}
          {sel("source_id", m("source"), "All sources")}
          {extra && sel("status", [...meta.pipeline, ...meta.terminal].map((s) => ({ value: s, label: s })), "Any status")}
        </div>
      )}
    </div>
  );
}

const Exp = ({ type, f }) => <Button size="sm" variant="outline" onClick={() => download(`/reports/${type}`, f)} data-testid={`an-export-${type}`}><Download className="mr-1.5 h-3.5 w-3.5" />Export</Button>;

function Bars({ data, x, bars, height = 280, layout }) {
  if (!data?.length) return <EmptyState title="No data for this selection" />;
  const v = layout === "vertical";
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout={layout} margin={{ left: v ? 30 : 0 }}>
        <CartesianGrid stroke="#EEF1F5" vertical={!v} horizontal={v ? false : true} />
        {v ? <><XAxis type="number" tick={axis} allowDecimals={false} /><YAxis type="category" dataKey={x} tick={axis} width={140} /></> : <><XAxis dataKey={x} tick={axis} interval={0} angle={data.length > 6 ? -25 : 0} textAnchor={data.length > 6 ? "end" : "middle"} height={data.length > 6 ? 70 : 30} /><YAxis tick={axis} allowDecimals={false} /></>}
        <Tooltip cursor={{ fill: "#F3F6FA" }} content={<ChartTip />} /><Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, color: "#4B5361" }} />
        {bars.map(([k, l], i) => <Bar key={k} dataKey={k} name={l} fill={COLORS[i % COLORS.length]} radius={[4, 4, 0, 0]} maxBarSize={36} />)}
      </BarChart>
    </ResponsiveContainer>
  );
}

const cyc = [{ key: "name", label: "Group" }, { key: "count", label: "Hires" }, { key: "avg", label: "Average (days)", render: (r) => n(r.avg) }, { key: "median", label: "Median (days)", render: (r) => n(r.median) }];

export default function Analytics() {
  const { can } = useAuth();
  const [params] = useSearchParams();
  const [f, setF] = useState({});
  const { data: d, loading } = useFetch("/analytics", f);
  if (loading && !d) return <PageLoader label="Crunching analytics" />;
  return (
    <div>
      <PageHeader eyebrow="Insights" title="Recruitment Analytics" description="Every metric is computed live from portal records. Funnel counts distinct applications — never interview rounds." />
      <Filters f={f} setF={setF} />
      {d && <Tabs defaultValue={params.get("tab") || "exec"}>
        <TabsList className="mb-1 flex w-full max-w-full justify-start">
          {[["exec", "Executive"], ["aph", "Age per Hire"], ["funnel", "Funnel"], ["recruiters", "Recruiters"], ["roles", "Roles & Departments"], ["sources", "Sources & Partners"], ...(d.cost ? [["cost", "Cost per Hire"]] : []), ["cycle", "Cycle Time (effective start)"]].map(([v, l]) => <TabsTrigger key={v} value={v} data-testid={`an-tab-${v}`}>{l}</TabsTrigger>)}
        </TabsList>
        <TabsContent value="exec" className="space-y-4">
          <KpiGrid k={d.kpis} cost={can("cost.view") ? d.cost : undefined} aph={d.aph} cycle={d.cycle} />
          <Section title="Monthly hiring trends">
            {!d.trends.length ? <EmptyState title="No trend data" /> : <ResponsiveContainer width="100%" height={260}><LineChart data={d.trends}><CartesianGrid stroke="#EEF1F5" vertical={false} /><XAxis dataKey="month" tick={axis} tickLine={false} /><YAxis tick={axis} allowDecimals={false} tickLine={false} axisLine={false} /><Tooltip content={<ChartTip />} /><Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, color: "#4B5361" }} />
              <Line dataKey="applications" name="Applications" stroke={BRAND.deep} strokeWidth={2.2} dot={{ r: 2.5 }} /><Line dataKey="offers" name="Offers" stroke={BRAND.blue} strokeWidth={2} dot={{ r: 2.5 }} /><Line dataKey="joined" name="Joined" stroke={STATUS.positive} strokeWidth={2} dot={{ r: 2.5 }} /></LineChart></ResponsiveContainer>}
          </Section>
        </TabsContent>
        <TabsContent value="aph"><AphDetail aph={d.aph} f={f} canExport={can("reports.export")} /></TabsContent>
        <TabsContent value="funnel"><Section title="Recruitment funnel (distinct applications)" actions={<Exp type="funnel" f={f} />}><FunnelChart funnel={d.funnel} />
          <p className="mt-4 text-[11px] text-[#9AA2AE]">Conversion = stage count ÷ previous stage. Rejected applications count toward the stages they reached (e.g. CV Rejected → screened).</p></Section></TabsContent>
        <TabsContent value="recruiters" className="space-y-4">
          <Section title="Recruiter performance" actions={<Exp type="recruiters" f={f} />}><Bars data={d.recruiters} x="name" bars={[["total", "Managed"], ["in_process", "In process"], ["selected", "Selected"], ["offers_released", "Offers"], ["offers_accepted", "Accepted"], ["joined", "Joined"]]} /></Section>
          <DataTable testid="an-recruiter-table" data={d.recruiters} columns={[{ key: "name", label: "Recruiter" }, { key: "total", label: "Managed" }, { key: "in_process", label: "In process" }, { key: "selected", label: "Selected" }, { key: "offers_released", label: "Offers released" }, { key: "offers_accepted", label: "Accepted" }, { key: "joined", label: "Joined" },
            { key: "conversion", label: "Conversion", render: (r) => n(r.conversion, "%") }, { key: "avg_cycle", label: "Avg cycle (d)", render: (r) => n(r.avg_cycle) }, ...(d.cost ? [{ key: "cost_per_hire", label: "Cost / hire", render: (r) => (r.cost_per_hire === null ? "N/A" : lakhs(r.cost_per_hire)) }] : []), { key: "workload", label: "Workload" }, { key: "open_requisitions", label: "Open reqs" }]} />
        </TabsContent>
        <TabsContent value="roles" className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <Section title="Filled vs open positions by role"><Bars data={d.roles.filter((r) => r.positions)} x="title" layout="vertical" height={Math.max(240, d.roles.length * 28)} bars={[["filled", "Filled"], ["open", "Open"]]} /></Section>
            <Section title="Department-wise recruitment" actions={<Exp type="departments" f={f} />}><Bars data={d.departments} x="department" bars={[["positions", "Positions"], ["candidates", "Candidates"], ["joined", "Joined"]]} /></Section>
          </div>
          <DataTable testid="an-role-table" data={d.roles} columns={[{ key: "code", label: "Req" }, { key: "title", label: "Role" }, { key: "department", label: "Department" }, { key: "status", label: "Status" }, { key: "positions", label: "Positions" }, { key: "filled", label: "Filled" }, { key: "open", label: "Open" }, { key: "candidates", label: "Candidates" }, { key: "in_process", label: "In process" }, { key: "avg_cycle", label: "Avg cycle (d)", render: (r) => n(r.avg_cycle) }, { key: "age_days", label: "Age (d)" }]} />
        </TabsContent>
        <TabsContent value="sources" className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-[1fr_1.4fr]">
            <Section title="Candidates by source">{!d.sources.length ? <EmptyState /> : <ResponsiveContainer width="100%" height={260}><PieChart><Pie data={d.sources} dataKey="total" nameKey="source" innerRadius={55} outerRadius={95} paddingAngle={2}>{d.sources.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} stroke="#fff" strokeWidth={2} />)}</Pie><Tooltip content={<ChartTip />} /><Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, color: "#4B5361" }} /></PieChart></ResponsiveContainer>}</Section>
            <Section title="Source conversion" actions={<Exp type="sources" f={f} />}><Bars data={d.sources} x="source" bars={[["screened", "Screened"], ["interviewed", "Interviewed"], ["offers_released", "Offers"], ["joined", "Joined"]]} /></Section>
          </div>
          <DataTable testid="an-source-table" data={d.sources} columns={[{ key: "source", label: "Source" }, { key: "total", label: "Sourced" }, { key: "screening_conversion", label: "Screening conv.", render: (r) => n(r.screening_conversion, "%") }, { key: "interview_conversion", label: "Interview conv.", render: (r) => n(r.interview_conversion, "%") }, { key: "offers_released", label: "Offers" }, { key: "joined", label: "Joined" }]} />
          <DataTable testid="an-partner-table" data={d.partners} emptyTitle="No consultancy-sourced applications" columns={[{ key: "partner", label: "Recruitment partner" }, { key: "total", label: "Candidates" }, { key: "interviewed", label: "Interviewed" }, { key: "offers_released", label: "Offers" }, { key: "joined", label: "Successful hires" }, ...(d.cost ? [{ key: "total_cost", label: "Total cost", render: (r) => lakhs(r.total_cost) }, { key: "cost_per_hire", label: "Cost / hire", render: (r) => (r.cost_per_hire === null ? "N/A" : lakhs(r.cost_per_hire)) }] : [])]} />
        </TabsContent>
        {d.cost && <TabsContent value="cost" className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-4">
            <Kpi label="Total hiring cost" value={lakhs(d.cost.total)} hint={`CTC ${lakhs(d.cost.ctc_total)} + fees ${lakhs(d.cost.fees)} · ${d.cost.hires} of ${d.cost.joined} hires confirmed`} testid="an-cost-total" /><Kpi label="Hires counted" value={`${d.cost.hires} / ${d.cost.joined}`} hint="Joined with confirmed cost / all joined" />
            <Kpi label="Average cost per hire" value={d.cost.cost_per_hire === null ? "N/A" : lakhs(d.cost.cost_per_hire)} hint="CTC + consulting + recruiter fees, averaged" testid="an-cost-per-hire" /><Kpi label="Invoices paid" value={lakhs(d.cost.paid)} />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Section title="Invoiced fees by category"><Bars data={d.cost.by_category} x="category" bars={[["amount", "₹ L"]]} /></Section>
            <Section title="Cost by month"><Bars data={d.cost.by_month} x="month" bars={[["amount", "₹ L"]]} /></Section>
          </div>
        </TabsContent>}
        <TabsContent value="cycle" className="space-y-4">
          <p className="text-xs text-subtle" data-testid="an-cycle-label">{d.cycle.label || "Recruitment cycle time — not Age per Hire"}. The official KPI is Age per Hire (Actual DOJ − CRF Raised Date).</p>
          <div className="grid gap-3 sm:grid-cols-4">
            <Kpi label="Avg cycle time" value={num(d.cycle.completed.avg, " d")} hint="Actual DOJ − earlier of CRF / initiation" testid="an-cycle-avg" /><Kpi label="Median cycle time" value={num(d.cycle.completed.median, " d")} />
            <Kpi label="Avg current age (open)" value={num(d.cycle.current_age.avg, " d")} hint="Today − effective start" /><Kpi label="Median current age" value={num(d.cycle.current_age.median, " d")} />
          </div>
          {d.cycle.missing_join_date > 0 && <p className="text-xs text-amber-700">{d.cycle.missing_join_date} joined candidate(s) have no actual date of joining and are excluded from cycle time.</p>}
          <p className="text-[11px] text-[#9AA2AE]">Effective start: CRF Raised Date when recruitment began on/after it; Recruitment Initiation Date when no CRF exists or the CRF was raised after recruitment had already started.</p>
          <div className="grid gap-4 lg:grid-cols-2">
            {[["by_role", "By role"], ["by_department", "By department"], ["by_recruiter", "By recruiter"], ["by_source", "By source"]].map(([k, l]) => <div key={k}><p className="eyebrow mb-2">{l}</p><DataTable testid={`an-cycle-${k}`} data={d.cycle[k]} columns={cyc} pageSize={6} /></div>)}
          </div>
          <div><p className="eyebrow mb-2">Oldest open applications (current recruitment age)</p><DataTable testid="an-cycle-oldest" data={d.cycle.oldest_active} pageSize={8} columns={[{ key: "candidate", label: "Candidate" }, { key: "role", label: "Role" }, { key: "status", label: "Stage" }, { key: "age", label: "Age (days)" }]} /></div>
        </TabsContent>
      </Tabs>}
    </div>
  );
}
