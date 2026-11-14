import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AlertTriangle, BadgeCheck, Briefcase, CalendarClock, CalendarDays, CheckCircle2, ChevronRight, ClipboardCheck, Clock3, Download, FileText, Loader2, PauseCircle, Search, UserCheck, Users } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useFetch } from "@/lib/useFetch";
import { PageHeader } from "@/components/common/Page";
import { StatusBadge } from "@/components/common/StatusBadge";
import { SelectField } from "@/components/common/FormDialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { CountUp, ChartTip, Delta, EASE, Pills, SegBar, SERIES, TONE, Tile, Unavailable, bucketLabel, useMounted } from "@/components/bento";
import { AXIS, BRAND, NEUTRAL, STATUS } from "@/lib/brand";
import { download, fmtDate, fmtDateTime } from "@/lib/api";
import { cn } from "@/lib/utils";
import { PageLoader } from "@/components/common/Loader";

const PERIODS = [["7d", "Last 7 days"], ["30d", "Last 30 days"], ["90d", "Last 90 days"], ["quarter", "This quarter"], ["year", "This year"], ["custom", "Custom range"]];
const KPI_ICON = { candidates: Users, open_requisitions: Briefcase, hires: UserCheck, screening: Search, interview: CalendarDays, offers_released: FileText, offers_accepted: CheckCircle2 };
const BLUES = [BRAND.deep, BRAND.royal, BRAND.blue, BRAND.sky, "#C9E6FD", NEUTRAL.grey, NEUTRAL.soft, "#E3E7EC"];
const STAGE_TONE = { Joined: STATUS.positive, "CV Rejected": STATUS.negative, "Interview Rejected": STATUS.negative, "Candidate Withdrawn": "#D99A97",
  "Offer Declined": "#D99A97", "Offer Revoked": "#D99A97", "No Show": "#D99A97", "On Hold": STATUS.warning };
const lk = (v) => (v == null ? "—" : `₹${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2 })} L`);
const rupees = (l) => (l == null ? "—" : `₹${Math.round(Number(l) * 100000).toLocaleString("en-IN")}`);
const linkCls = "text-[13px] font-medium text-brand-royal hover:text-brand-deep";

/* ---------- interviewer view (also "My interviews" for Recruiters and Management) ---------- */
function InterviewerHome() {
  const { data } = useFetch("/interviews", { mine: "true" });
  const rows = data || [];
  const upcoming = rows.filter((i) => ["Scheduled", "Rescheduled"].includes(i.status));
  const pending = rows.filter((i) => i.my_pending?.length && i.status !== "Cancelled");
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Tile title={`Upcoming interviews · ${upcoming.length}`} testid="my-upcoming">
        {!upcoming.length ? <Unavailable>No upcoming interviews</Unavailable> : upcoming.map((i) => (
          <Link to="/interviews" key={i.id} className="flex items-center justify-between gap-3 rounded-[10px] px-2 py-2.5 transition-colors hover:bg-[#F3F6FA]">
            <div className="min-w-0"><p className="truncate text-[14px] font-medium">{i.candidate_name}</p><p className="truncate text-[12px] text-subtle">{i.round_name} · {i.requisition_title}</p></div>
            <p className="shrink-0 text-[12px] tabular-nums text-[#4B5361]">{fmtDate(i.date)} {i.start_time}</p>
          </Link>))}
      </Tile>
      <Tile title={`Feedback pending · ${pending.length}`} testid="my-pending-feedback" action={<Link to="/interviews" className={linkCls}>Open interviews</Link>}>
        {!pending.length ? <Unavailable>Nothing pending</Unavailable> : pending.map((i) => (
          <Link to="/interviews" key={i.id} className="flex items-center justify-between gap-3 rounded-[10px] px-2 py-2.5 hover:bg-[#F3F6FA]">
            <p className="min-w-0 truncate text-[14px]">{i.candidate_name} · <span className="text-subtle">{i.round_name}</span></p><StatusBadge status={i.status} />
          </Link>))}
      </Tile>
    </div>
  );
}

/* ---------- header filters ---------- */
function Filters({ f, setF, reqs, exportMenu }) {
  const { list } = useAuth();
  const m = (t) => list(t).map((x) => ({ value: x.id, label: x.name }));
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="dashboard-filters">
      <div className="relative">
        <CalendarDays className="pointer-events-none absolute left-3 top-2.5 z-[1] h-4 w-4 text-subtle" />
        <SelectField value={f.period} onChange={(v) => setF({ ...f, period: v || "30d" })} options={PERIODS.map(([value, label]) => ({ value, label }))} allowNone={false} testid="period" className="w-[170px] pl-9" />
      </div>
      {f.period === "custom" && (
        <span className="flex items-center gap-1.5">
          <Input type="date" className="h-9 w-[148px]" value={f.date_from || ""} max={f.date_to || undefined} onChange={(e) => setF({ ...f, date_from: e.target.value })} data-testid="period-from" />
          <span className="text-[12px] text-subtle">to</span>
          <Input type="date" className="h-9 w-[148px]" value={f.date_to || ""} min={f.date_from || undefined} onChange={(e) => setF({ ...f, date_to: e.target.value })} data-testid="period-to" />
        </span>
      )}
      <SelectField value={f.department_id} onChange={(v) => setF({ ...f, department_id: v })} options={m("department")} placeholder="All departments" testid="dash-filter-department" className="w-[164px]" />
      <SelectField value={f.requisition_id} onChange={(v) => setF({ ...f, requisition_id: v })} options={(reqs || []).map((r) => ({ value: r.id, label: `${r.code} · ${r.title}` }))} placeholder="All requisitions" testid="dash-filter-requisition" className="w-[176px]" />
      <SelectField value={f.recruiter_id} onChange={(v) => setF({ ...f, recruiter_id: v })} options={m("recruiter")} placeholder="All recruiters" testid="dash-filter-recruiter" className="w-[160px]" />
      {exportMenu}
    </div>
  );
}

/* ---------- KPI row ---------- */
function KpiRow({ d }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 min-[1380px]:grid-cols-7" data-testid="dashboard-hero">
      {d.hero.map((h) => {
        const Icon = KPI_ICON[h.key] || Users;
        return (
          <Link key={h.key} to={h.link} data-testid={`hero-${h.key}`}
            className="group flex min-w-0 items-start gap-2.5 rounded-2xl border border-line bg-white p-3.5 shadow-[0_1px_2px_rgba(32,36,43,0.04)] transition-[border-color,box-shadow] duration-200 hover:border-[#CFE3FB] hover:shadow-[0_10px_24px_-18px_rgba(34,101,200,0.55)]">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-[10px] bg-brand-pale text-brand-deep transition-colors group-hover:bg-[#E1EEFD] min-[1380px]:hidden min-[1600px]:grid"><Icon className="h-[18px] w-[18px]" strokeWidth={1.7} /></span>
            <span className="min-w-0">
              <span className="block truncate text-[13px] font-medium text-[#4B5361]" title={h.label}>{h.label}</span>
              <span className="mt-0.5 flex flex-wrap items-baseline gap-x-2">
                <span className="text-[28px] font-semibold leading-none tracking-[-0.02em] text-ink"><CountUp value={h.value} testid={`hero-${h.key}-value`} /></span>
                <Delta pct={h.change_pct} />
              </span>
              <span className="mt-1 block truncate text-[12px] text-subtle" title={h.flow ? `${h.previous_count} in the previous period` : `${h.period_count} ${h.note}`}>
                {h.flow ? `${h.note.replace(" in period", "")} · prev. ${h.previous_count}` : `${h.period_count} ${h.note}`}
              </span>
              {h.detail && <span className="mt-0.5 block text-[12px] font-medium leading-snug text-brand-deep" data-testid={`hero-${h.key}-detail`}
                title={h.key === "candidates" ? "Candidates attached to at least one requisition" : "One person joined on more than one requisition"}>{h.detail}</span>}
            </span>
          </Link>
        );
      })}
    </div>
  );
}

/* ---------- performance trend ---------- */
function TrendTile({ d, gran, setGran }) {
  const series = d.trend.series;
  const [hidden, setHidden] = useState({});
  const pts = d.trend.points;
  const empty = !pts.some((p) => series.some((s) => p[s.key] > 0));
  return (
    <Tile title="Recruitment performance trend" info="Counts of each event dated inside the selected period" className="lg:col-span-7" testid="dashboard-trend"
      action={<Pills label="Granularity" value={gran} options={[["week", "Weekly"], ["month", "Monthly"]]} onChange={setGran} testid="granularity" />}>
      {empty ? <Unavailable className="min-h-[260px]">No recruitment activity recorded in this period</Unavailable> : (
        <div className="h-[270px]" data-testid="trend-chart">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={pts} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
              <defs>
                {series.map((s) => (
                  <linearGradient key={s.key} id={`g-${s.key}`} x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0" stopColor={SERIES[s.key]} stopOpacity={s.key === "added" ? 0.22 : 0.08} />
                    <stop offset="1" stopColor={SERIES[s.key]} stopOpacity={0} />
                  </linearGradient>))}
              </defs>
              <CartesianGrid vertical={false} stroke="#EEF1F5" />
              <XAxis dataKey="bucket" tick={AXIS} tickLine={false} axisLine={{ stroke: NEUTRAL.line }} tickFormatter={(k) => bucketLabel(k, gran)} minTickGap={16} />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} width={34} />
              <Tooltip cursor={{ stroke: BRAND.sky, strokeWidth: 1.5 }} content={<ChartTip labelFormat={(k) => (gran === "week" ? `Week of ${bucketLabel(k, gran)}` : bucketLabel(k, gran))} />} />
              {series.filter((s) => !hidden[s.key]).map((s) => (
                <Area key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={SERIES[s.key]} strokeWidth={s.key === "added" ? 2.5 : 2}
                  fill={`url(#g-${s.key})`} dot={{ r: 2.5, strokeWidth: 0, fill: SERIES[s.key] }} activeDot={{ r: 4.5, strokeWidth: 2, stroke: "#fff" }} animationDuration={800} />))}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
      <div className="mt-3 flex flex-wrap justify-center gap-x-5 gap-y-2" role="group" aria-label="Series — click to show or hide">
        {series.map((s) => (
          <button key={s.key} type="button" onClick={() => setHidden({ ...hidden, [s.key]: !hidden[s.key] })} aria-pressed={!hidden[s.key]} data-testid={`trend-toggle-${s.key}`}
            className={cn("flex items-center gap-1.5 rounded-md text-[13px] text-[#4B5361] transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-royal/40", hidden[s.key] && "opacity-40")}>
            <i className="h-2.5 w-2.5 rounded-full" style={{ background: SERIES[s.key] }} />{s.label}
            <b className="font-semibold tabular-nums text-ink">{pts.reduce((t, p) => t + p[s.key], 0)}</b>
          </button>
        ))}
      </div>
    </Tile>
  );
}

/* ---------- funnel ---------- */
function FunnelTile({ d }) {
  const nav = useNavigate();
  const mounted = useMounted();
  const st = d.funnel.stages;
  const n = st.length;
  return (
    <Tile title={<span className="flex flex-col">Recruitment funnel{d.funnel.cohort ? <span className="text-[13px] font-normal text-subtle" data-testid="funnel-cohort">{d.funnel.cohort} application{d.funnel.cohort === 1 ? "" : "s"} from {d.funnel.cohort_candidates} candidate{d.funnel.cohort_candidates === 1 ? "" : "s"}</span> : null}</span>} info="Applications created in the period; each stage counts applications that reached it" className="lg:col-span-5" testid="dashboard-funnel"
      action={<span className="rounded-full bg-brand-pale px-3 py-1 text-[13px] font-semibold text-brand-deep" data-testid="funnel-overall">Overall conversion: {d.funnel.overall_conversion == null ? "—" : `${d.funnel.overall_conversion}%`}</span>}>
      {!d.funnel.cohort ? <Unavailable className="min-h-[260px]">No applications created in this period</Unavailable> : (
        <div className="grid grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)] gap-x-4">
          <div className="flex flex-col items-center gap-[3px]">
            {st.map((s, i) => {
              const top = 100 - i * (32 / n), bot = 100 - (i + 1) * (32 / n);
              const inset = (100 - bot / top * 100) / 2;
              return (
                <button key={s.stage} type="button" onClick={() => nav(`/pipeline?status=${encodeURIComponent(s.statuses.join(","))}`)} data-testid={`funnel-stage-${s.stage.toLowerCase().replace(/ /g, "-")}`}
                  title={`Open ${s.stage} in the pipeline`}
                  className="group relative flex h-[28px] items-center justify-between gap-2 px-[9%] text-[12.5px] font-semibold transition-[filter,width] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-royal/40 hover:brightness-95"
                  style={{ width: mounted ? `${top}%` : "40%", clipPath: `polygon(0 0, 100% 0, ${100 - inset}% 100%, ${inset}% 100%)`,
                    background: i === n - 1 ? "#1B4F9C" : [BRAND.sky, "#93CDFB", "#86C5F9", BRAND.blue, "#5AA4EE", "#4C93E5", BRAND.royal][Math.min(i, 6)],
                    color: i >= 3 ? "#fff" : "#16325C", transition: `width 700ms ${EASE} ${i * 50}ms` }}>
                  <span className="truncate">{s.stage}</span><span className="tabular-nums">{s.count}</span>
                </button>
              );
            })}
          </div>
          <table className="self-start text-[12.5px]">
            <thead><tr className="text-[11.5px] text-subtle"><th className="pb-1 text-right font-medium">Conversion</th><th className="pb-1 text-right font-medium">Drop-off</th></tr></thead>
            <tbody>
              {st.map((s, i) => {
                const next = st[i + 1];
                return (
                  <tr key={s.stage} className="h-[31px] border-b border-[#EEF1F5] last:border-0">
                    <td className="text-right tabular-nums text-ink">{next ? (next.conversion == null ? "—" : `${next.conversion}%`) : ""}</td>
                    <td className="text-right tabular-nums text-[#4B5361]">{next ? (next.drop_off ? <>{next.drop_off}<span className="ml-1 text-[11px] text-subtle">({(100 - (next.conversion ?? 100)).toFixed(1)}%)</span></> : "0") : ""}</td>
                  </tr>);
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-3 text-[12px] text-subtle">Counts applications (one candidate can apply to several requisitions) · conversion to the next stage · click a stage to open it</p>
    </Tile>
  );
}

/* ---------- sparkline ---------- */
function Spark({ data, dataKey, name, format, gran }) {
  const pts = data.filter((t) => t[dataKey] != null);
  if (pts.length < 2) return <Unavailable className="h-full py-2 text-[12px]">{pts.length ? "Trend appears once two or more periods have data" : "No data in this period"}</Unavailable>;
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 6, right: 6, left: 6, bottom: 0 }}>
        <defs><linearGradient id={`sp-${dataKey}-${name.length}`} x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor={BRAND.royal} stopOpacity={0.25} /><stop offset="1" stopColor={BRAND.royal} stopOpacity={0} /></linearGradient></defs>
        <XAxis dataKey="bucket" hide />
        <Tooltip cursor={{ stroke: BRAND.sky }} content={<ChartTip labelFormat={(k) => bucketLabel(k, gran)} valueFormat={(v, p) => `${format(v)} · ${p.payload.hires} hire(s)`} />} />
        <Area type="monotone" dataKey={dataKey} name={name} stroke={BRAND.deep} strokeWidth={2} fill={`url(#sp-${dataKey}-${name.length})`} dot={{ r: 2.5, fill: BRAND.deep, strokeWidth: 0 }} connectNulls animationDuration={800} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function Flag({ children, testid }) {
  return <p className="mt-3 flex items-start gap-1.5 rounded-[10px] border border-[#F0DFBD] bg-[#FBF4E6] px-3 py-2 text-[12px] text-[#8A6420]" data-testid={testid}><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /><span>{children}</span></p>;
}

function CostTile({ c, gran }) {
  const parts = [["Total candidate CTC", c.ctc_total], ["Consulting fees", c.consulting_total], ["Recruiter fees", c.recruiter_total]];
  return (
    <Tile title="Cost per hire" info="Cost per hire = Candidate CTC + Consulting fees + Recruiter fees; average over joined hires with confirmed cost" className="lg:col-span-6" testid="dashboard-cost"
      action={<Link to="/costs" className={linkCls}>Details</Link>}>
      <div className="grid gap-4 min-[1600px]:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div className="min-w-0">
          <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
            <div>
              <p className="text-[32px] font-semibold leading-none tracking-[-0.02em]" data-testid="dash-cost-avg">{c.cost_per_hire == null ? "N/A" : <CountUp value={c.cost_per_hire} format={(v) => rupees(v)} />}</p>
              <p className="mt-1 text-[13px] text-subtle">Average cost per hire</p>
            </div>
            <div className="border-l border-line pl-6">
              <p className="text-[20px] font-semibold tabular-nums" data-testid="dash-cost-total">{lk(c.total)}</p>
              <p className="mt-0.5 text-[13px] text-subtle">Total recruitment cost</p>
            </div>
          </div>
          <dl className="mt-4 grid grid-cols-3 gap-2">
            {parts.map(([l, v]) => (
              <div key={l} className="min-w-0 rounded-[10px] border border-line bg-canvas px-3 py-2">
                <dd className="truncate text-[14px] font-semibold tabular-nums">{lk(v)}</dd>
                <dt className="truncate text-[12px] text-subtle">{l}</dt>
              </div>))}
          </dl>
          <p className="mt-2 text-[12px] text-subtle">{c.hires} of {c.joined} joined hire(s) with confirmed cost</p>
        </div>
        <div className="h-[96px] min-w-0 min-[1600px]:h-[130px]"><Spark data={c.trend} dataKey="avg" name="Avg cost per hire" format={lk} gran={gran} /></div>
      </div>
      {(c.unconfirmed > 0 || c.pending_confirmation > 0) && <Flag testid="dash-cost-incomplete">{c.unconfirmed > 0 && `${c.unconfirmed} joined hire(s) have no confirmed cost and are excluded. `}{c.pending_confirmation > 0 && `${c.pending_confirmation} accepted offer(s) await cost confirmation.`}</Flag>}
    </Tile>
  );
}

function AgeTile({ a, gran }) {
  const c = a.completed;
  const days = (v) => (v == null ? "—" : `${Number.isInteger(v) ? v : v.toFixed(1)} days`);
  return (
    <Tile title="Age per hire" info="Actual date of joining − CRF raised date, in calendar days" className="lg:col-span-6" testid="dashboard-aph"
      action={<Link to="/analytics?tab=aph" className={linkCls}>Full analysis</Link>}>
      <div className="grid gap-4 min-[1600px]:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div className="min-w-0">
          <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
            <div>
              <p className="text-[32px] font-semibold leading-none tracking-[-0.02em]" data-testid="dash-aph-average">{c.avg == null ? "—" : <CountUp value={c.avg} format={(x) => `${Number.isInteger(c.avg) ? Math.round(x) : x.toFixed(1)} days`} />}</p>
              <p className="mt-1 text-[13px] text-subtle">Average age per hire</p>
            </div>
            <div className="border-l border-line pl-6"><p className="text-[20px] font-semibold tabular-nums" data-testid="dash-aph-fastest">{days(c.min)}</p><p className="mt-0.5 text-[13px] text-subtle">Minimum</p></div>
            <div className="border-l border-line pl-6"><p className="text-[20px] font-semibold tabular-nums" data-testid="dash-aph-longest">{days(c.max)}</p><p className="mt-0.5 text-[13px] text-subtle">Maximum</p></div>
          </div>
          {a.by_requisition.length > 0 && (
            <ul className="mt-4 space-y-1.5" data-testid="aph-by-requisition">
              {a.by_requisition.slice(0, 3).map((r) => (
                <li key={r.requisition} className="flex items-center justify-between gap-3 text-[13px]">
                  <span className="min-w-0 truncate text-[#4B5361]"><span className="text-[12px] text-subtle">{r.requisition}</span> {r.role}</span>
                  <span className="shrink-0 tabular-nums text-ink">{r.avg} d <span className="text-subtle">· {r.hires}</span></span>
                </li>))}
            </ul>)}
          <p className="mt-2 text-[12px] text-subtle">{c.count} completed hire(s)</p>
        </div>
        <div className="h-[96px] min-w-0 min-[1600px]:h-[130px]"><Spark data={a.trend} dataKey="avg" name="Avg age per hire" format={(v) => `${v} days`} gran={gran} /></div>
      </div>
      {(a.missing_crf.length > 0 || a.flagged > 0) && <Flag testid="dash-aph-flags">{a.missing_crf.length > 0 && `${a.missing_crf.length} open requisition(s) have no CRF raised date. `}{a.flagged > 0 && `${a.flagged} hire(s) excluded for missing or invalid dates.`}</Flag>}
    </Tile>
  );
}

/* ---------- sources (donut) ---------- */
function SourcesTile({ s }) {
  const nav = useNavigate();
  const total = s.reduce((t, x) => t + x.candidates, 0);
  const go = (id) => id && nav(`/candidates?source_id=${id}`);
  return (
    <Tile title="Recruitment source analytics" info="Candidates, shortlisted and hires by source for applications created in the period" className="lg:col-span-4" testid="dashboard-sources">
      {!s.length ? <Unavailable>No candidates in this period</Unavailable> : (
        <div className="grid items-center gap-4 sm:grid-cols-[150px_minmax(0,1fr)] lg:grid-cols-1">
          <div className="relative mx-auto h-[150px] w-[150px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={s} dataKey="candidates" nameKey="source" innerRadius={50} outerRadius={72} paddingAngle={1.5} stroke="#fff" strokeWidth={2} animationDuration={800}
                  onClick={(x) => go(x?.source_id || x?.payload?.source_id)} cursor="pointer">
                  {s.map((x, i) => <Cell key={x.source} fill={BLUES[i % BLUES.length]} />)}
                </Pie>
                <Tooltip content={<ChartTip valueFormat={(v) => `${v} candidate(s)`} />} />
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
              <span><span className="block text-[22px] font-semibold leading-none tabular-nums">{total}</span><span className="text-[11.5px] text-subtle">candidates</span></span>
            </div>
          </div>
          <table className="w-full text-[13px]">
            <thead><tr className="text-[11.5px] text-subtle"><th className="pb-1 text-left font-medium">Source</th><th className="pb-1 text-right font-medium">Share</th><th className="pb-1 text-right font-medium">Cand.</th><th className="pb-1 text-right font-medium">Short.</th><th className="pb-1 text-right font-medium">Hired</th></tr></thead>
            <tbody>
              {s.map((x, i) => (
                <tr key={x.source} onClick={() => go(x.source_id)} className={cn(x.source_id && "cursor-pointer hover:bg-[#F7FAFF]")} data-testid={`source-row-${x.source}`}>
                  <td className="py-1"><span className="flex min-w-0 items-center gap-2"><i className="h-2.5 w-2.5 shrink-0 rounded-[3px]" style={{ background: BLUES[i % BLUES.length] }} /><span className="truncate">{x.source}</span></span></td>
                  <td className="py-1 text-right tabular-nums text-subtle">{total ? Math.round((x.candidates / total) * 100) : 0}%</td>
                  <td className="py-1 text-right font-semibold tabular-nums">{x.candidates}</td>
                  <td className="py-1 text-right tabular-nums">{x.shortlisted}</td>
                  <td className="py-1 text-right tabular-nums">{x.joined}</td>
                </tr>))}
            </tbody>
          </table>
        </div>)}
    </Tile>
  );
}

/* ---------- recruiters ---------- */
function RecruitersTile({ r, showCost }) {
  const nav = useNavigate();
  const [metric, setMetric] = useState("assigned");
  const [more, setMore] = useState(false);
  const opts = [["assigned", "Assigned"], ["screened", "Screened"], ["interviews", "Interviews"], ["offers_released", "Offers"], ["joined", "Joined"]];
  const data = [...r].sort((a, b) => b[metric] - a[metric]).slice(0, 6);
  const max = Math.max(1, ...data.map((x) => x[metric]));
  const mounted = useMounted();
  return (
    <Tile title="Recruiter performance" info="Measured outcomes only — no scores" className="lg:col-span-4" testid="dashboard-recruiters"
      action={<SelectField value={metric} onChange={(v) => setMetric(v || "assigned")} options={opts.map(([value, label]) => ({ value, label }))} allowNone={false} testid="recruiter-metric" className="h-8 w-[130px] text-[13px]" />}>
      {!data.length ? <Unavailable>No recruiter activity in this period</Unavailable> : (
        <>
          <ul className="space-y-2.5">
            {data.map((x, i) => (
              <li key={x.name}>
                <button type="button" onClick={() => x.recruiter_id && nav(`/pipeline?recruiter_id=${x.recruiter_id}`)} className="grid w-full grid-cols-[minmax(0,118px)_1fr_32px] items-center gap-3 text-left text-[13px]">
                  <span className="truncate text-ink" title={x.name}>{x.name}</span>
                  <span className="h-3.5 rounded-[4px] bg-[#F1F4F8]"><span className="block h-3.5 rounded-[4px]" style={{ width: mounted ? `${Math.max(3, (x[metric] / max) * 100)}%` : "3%", background: [BRAND.deep, BRAND.royal, BRAND.blue, BRAND.sky, "#C9E6FD", "#C9E6FD"][i], transition: `width 700ms ${EASE} ${i * 50}ms` }} /></span>
                  <span className="text-right font-semibold tabular-nums">{x[metric]}</span>
                </button>
              </li>))}
          </ul>
          <button type="button" onClick={() => setMore(!more)} className="mt-3 self-start text-[13px] font-medium text-brand-royal hover:text-brand-deep" data-testid="recruiter-details-toggle">{more ? "Hide details" : "Show all measures"}</button>
          {more && (
            <div className="-mx-1 mt-2 overflow-x-auto">
              <table className="w-full min-w-[460px] text-[12.5px]">
                <thead><tr className="text-[11.5px] text-subtle">{["Recruiter", "Assigned", "Screened", "Interviews", "Offers", "Joined", "Age/hire", ...(showCost ? ["Cost/hire"] : [])].map((h, i) => <th key={h} className={cn("px-1 pb-1.5 font-medium", i ? "text-right" : "text-left")}>{h}</th>)}</tr></thead>
                <tbody>{r.map((x) => (
                  <tr key={x.name} className="border-t border-[#EEF1F5]">
                    <td className="max-w-[120px] truncate px-1 py-1.5">{x.name}</td>
                    {["assigned", "screened", "interviews", "offers_released", "joined"].map((k) => <td key={k} className="px-1 py-1.5 text-right tabular-nums">{x[k]}</td>)}
                    <td className="px-1 py-1.5 text-right tabular-nums">{x.avg_age_per_hire == null ? "—" : `${x.avg_age_per_hire} d`}</td>
                    {showCost && <td className="px-1 py-1.5 text-right tabular-nums">{x.cost_per_hire == null ? "—" : lk(x.cost_per_hire)}</td>}
                  </tr>))}</tbody>
              </table>
            </div>)}
        </>)}
    </Tile>
  );
}

/* ---------- requisitions ---------- */
const ageColor = (b) => (b === "90+ days" ? STATUS.negative : b === "61–90 days" ? STATUS.warning : b === "No CRF date" ? NEUTRAL.soft : b === "31–60 days" ? BRAND.blue : BRAND.deep);

function RequisitionsTile({ q, rf, setRf }) {
  const { list } = useAuth();
  const m = (t) => list(t).map((x) => ({ value: x.id, label: x.name }));
  const boxes = [["Open", q.open, Briefcase, "/requisitions?status=Open"], ["Approved", q.positions, BadgeCheck], ["Filled", q.filled, Users], ["On hold", q.on_hold, PauseCircle, "/requisitions?status=On Hold"]];
  return (
    <Tile title="Requisition analytics" info="Positions approved = positions on the requisitions in view; time to fill = last joining − CRF date for fully filled requisitions" className="lg:col-span-4" testid="dashboard-requisitions">
      <div className="mb-3 grid grid-cols-3 gap-1.5">
        <SelectField value={rf.hiring_manager_id} onChange={(v) => setRf({ ...rf, hiring_manager_id: v })} options={m("hiring_manager")} placeholder="Manager" testid="req-filter-hm" className="h-8 text-[12.5px]" />
        <SelectField value={rf.location_id} onChange={(v) => setRf({ ...rf, location_id: v })} options={m("location")} placeholder="Location" testid="req-filter-location" className="h-8 text-[12.5px]" />
        <SelectField value={rf.req_status} onChange={(v) => setRf({ ...rf, req_status: v })} options={["Open", "On Hold", "Closed", "Filled", "Cancelled"].map((s) => ({ value: s, label: s }))} placeholder="Status" testid="req-filter-status" className="h-8 text-[12.5px]" />
      </div>
      <div className="grid grid-cols-4 gap-1.5">
        {boxes.map(([l, v, Icon, href]) => {
          const inner = (<><Icon className="mx-auto h-4 w-4 text-brand-deep" strokeWidth={1.8} /><p className="mt-1 text-[20px] font-semibold leading-none tabular-nums">{v}</p><p className="mt-1 text-[12px] text-subtle">{l}</p></>);
          const cls = "rounded-[10px] border border-line px-1 py-2.5 text-center transition-colors";
          return href ? <Link key={l} to={href} className={cn(cls, "hover:border-[#CFE3FB] hover:bg-brand-mist")} data-testid={`req-stat-${l.toLowerCase().replace(/ /g, "-")}`}>{inner}</Link>
            : <div key={l} className={cls} data-testid={`req-stat-${l.toLowerCase().replace(/ /g, "-")}`}>{inner}</div>;
        })}
      </div>
      <div className="mt-4 grid grid-cols-2 divide-x divide-line">
        <div className="pr-3"><p className="text-[12px] text-subtle">Average time to fill</p><p className="text-[22px] font-semibold tabular-nums" data-testid="req-stat-avg-time-to-fill">{q.avg_time_to_fill == null ? "—" : `${q.avg_time_to_fill} days`}</p></div>
        <div className="pl-4"><p className="text-[12px] text-subtle">Positions remaining</p><p className="text-[22px] font-semibold tabular-nums" data-testid="req-stat-remaining">{q.remaining}</p></div>
      </div>
      <p className="mt-4 text-[12px] text-subtle">Open requisitions by age (today − CRF raised date)</p>
      <div className="mt-1.5"><SegBar items={q.ageing.map((x) => ({ key: x.bucket, label: x.bucket, value: x.count }))} height={10} colorOf={(x) => ageColor(x.key)} testid="req-ageing" /></div>
      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[11.5px] text-subtle">{q.ageing.filter((x) => x.count).map((x) => <span key={x.bucket} className="flex items-center gap-1"><i className="h-2 w-2 rounded-[2px]" style={{ background: ageColor(x.bucket) }} />{x.bucket} · {x.count}</span>)}</div>
      {q.oldest.length > 0 && (
        <ul className="mt-3 divide-y divide-[#EEF1F5]">
          {q.oldest.slice(0, 3).map((r) => (
            <li key={r.id}><Link to={`/requisitions/${r.id}`} className="flex items-center justify-between gap-3 py-1.5 text-[12.5px] hover:text-brand-deep">
              <span className="min-w-0 truncate"><span className="text-subtle">{r.code}</span> {r.title}</span>
              <span className="flex shrink-0 items-center gap-2 tabular-nums text-subtle">{r.filled}/{r.positions}<span className={cn(r.age > 90 && "font-medium text-[#C0504D]")}>{r.age == null ? "no CRF" : `${r.age} d`}</span></span>
            </Link></li>))}
        </ul>)}
    </Tile>
  );
}

/* ---------- operations ---------- */
function UpcomingTile({ items }) {
  return (
    <Tile title="Upcoming interviews" className="lg:col-span-4" testid="dashboard-upcoming" action={<Link to="/interviews" className={linkCls}>View all</Link>}>
      {!items.length ? <Unavailable>No interviews scheduled</Unavailable> : (
        <ul className="-mx-2 space-y-0.5">{items.map((i) => (
          <li key={i.id}><Link to="/interviews" className="flex gap-3 rounded-[10px] px-2 py-2 transition-colors hover:bg-[#F3F6FA]">
            <span className={cn("flex w-12 shrink-0 flex-col items-center justify-center rounded-[10px] py-1.5", i.today ? "bg-brand-deep text-white" : "bg-brand-pale text-brand-deep")}>
              <span className="text-[10px] font-medium uppercase">{i.today ? "Today" : new Date(`${i.date}T00:00:00`).toLocaleDateString("en-IN", { month: "short" })}</span>
              <span className="text-[14px] font-semibold leading-tight tabular-nums">{i.today ? (i.time || "—").slice(0, 5) : new Date(`${i.date}T00:00:00`).getDate()}</span>
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex items-center justify-between gap-2"><span className="truncate text-[14px] font-medium">{i.candidate}</span><StatusBadge status={i.status} /></span>
              <span className="block truncate text-[12px] text-subtle">{i.round} · {i.requisition}</span>
              <span className="block truncate text-[12px] text-subtle">{i.interviewers.join(", ") || "No interviewer"}{!i.today && i.time ? ` · ${i.time}` : ""}</span>
            </span>
          </Link></li>))}
        </ul>)}
    </Tile>
  );
}

const PENDING_ICON = { feedback: ClipboardCheck, to_schedule: CalendarClock, approval: BadgeCheck, acceptance: Clock3, cost: FileText };
function PendingTile({ items }) {
  const total = items.reduce((s, x) => s + x.count, 0);
  return (
    <Tile title="Pending actions" className="lg:col-span-3" testid="dashboard-pending" action={<span className="rounded-full bg-brand-pale px-2.5 py-0.5 text-[13px] font-semibold tabular-nums text-brand-deep">{total}</span>}>
      <ul className="-mx-2 space-y-0.5">{items.map((p) => {
        const Icon = PENDING_ICON[p.key] || ClipboardCheck;
        return (
          <li key={p.key}><Link to={p.link} data-testid={`pending-${p.key}`} className="group flex items-center gap-3 rounded-[10px] px-2 py-2 transition-colors hover:bg-[#F3F6FA]">
            <Icon className="h-4 w-4 shrink-0 text-subtle group-hover:text-brand-deep" strokeWidth={1.8} />
            <span className="min-w-0 flex-1 text-[13px] text-ink">{p.label}</span>
            <span className={cn("grid h-6 min-w-6 place-items-center rounded-full px-2 text-[12px] font-semibold tabular-nums", p.count ? "bg-brand-deep text-white" : "bg-[#F1F3F6] text-subtle")}>{p.count}</span>
            <ChevronRight className="h-4 w-4 shrink-0 text-[#C6CDD6]" />
          </Link></li>);
      })}</ul>
    </Tile>
  );
}

function ActivityTile({ items }) {
  return (
    <Tile title="Recent recruitment activity" className="lg:col-span-5" testid="dashboard-activity">
      {!items.length ? <Unavailable>No recent activity</Unavailable> : (
        <ol className="relative ml-1 space-y-3 border-l border-line pl-4">{items.slice(0, 7).map((x, i) => (
          <li key={i} className="relative">
            <span className={cn("absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full ring-2 ring-white", x.event === "Candidate joined" ? "bg-[#3E8E63]" : i === 0 ? "bg-brand-deep" : "bg-brand-sky")} />
            <Link to={`/candidates/${x.candidate_id}`} className="block rounded-[8px] hover:text-brand-deep">
              <span className="flex items-baseline justify-between gap-2"><span className="truncate text-[13.5px]"><b className="font-medium">{x.event}</b> · {x.candidate}</span><span className="shrink-0 text-[11.5px] tabular-nums text-subtle">{fmtDateTime(x.at)}</span></span>
              <span className="block truncate text-[12px] text-subtle">{x.requisition} · by {x.by}</span>
            </Link>
          </li>))}
        </ol>)}
    </Tile>
  );
}

function DistributionTile({ items, total }) {
  const nav = useNavigate();
  let blue = 0;
  const colors = Object.fromEntries(items.map((x) => [x.status, STAGE_TONE[x.status] || BLUES[Math.min(blue++, 5)]]));
  const activeCount = items.filter((x) => x.active).reduce((s, x) => s + x.count, 0);
  return (
    <Tile title="Candidate pipeline distribution" info="Current stage of every application in view" className="lg:col-span-12" testid="dashboard-distribution"
      action={<span className="text-[13px] text-subtle"><b className="font-semibold text-ink">{total}</b> applications · {activeCount} active · {total - activeCount} closed</span>}>
      {!items.length ? <Unavailable>No applications</Unavailable> : (
        <>
          <SegBar items={items.map((x) => ({ key: x.status, label: x.status, value: x.count }))} height={22} colorOf={(x) => colors[x.key]} onSelect={(x) => nav(`/pipeline?status=${encodeURIComponent(x.key)}`)} testid="distribution-bar" />
          <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5">
            {items.map((x) => (
              <li key={x.status}><Link to={`/pipeline?status=${encodeURIComponent(x.status)}`} className="flex items-center gap-1.5 text-[13px] text-[#4B5361] hover:text-brand-deep">
                <i className="h-2.5 w-2.5 rounded-[3px]" style={{ background: colors[x.status] }} />{x.status}<b className="font-semibold tabular-nums text-ink">{x.count}</b>
              </Link></li>))}
          </ul>
        </>)}
    </Tile>
  );
}

/* ---------- page ---------- */
export default function Dashboard() {
  const { user, can } = useAuth();
  const dual = can("analytics.view") && user.role !== "super_admin" && (user.roles || []).includes("interviewer");
  const [view, setView] = useState("overview");
  const [f, setF] = useState({ period: "30d" });
  const [gran, setGran] = useState(null);
  const [rf, setRf] = useState({});
  const customReady = f.period !== "custom" || (f.date_from && f.date_to);
  const params = useMemo(() => ({ ...f, ...rf, granularity: gran || undefined }), [f, rf, gran]);
  const { data: d, loading } = useFetch("/dashboard", params, can("analytics.view") && !!customReady);
  const { data: reqs } = useFetch("/requisitions", {}, can("analytics.view"));
  const g = d?.period.granularity || gran || "week";
  const exp = (type, extra = {}) => download(`/reports/${type}`, { date_from: d?.period.start, date_to: d?.period.end, department_id: f.department_id, recruiter_id: f.recruiter_id, requisition_id: f.requisition_id, ...extra });

  if (!can("analytics.view")) {
    return (<div><PageHeader title={`Welcome, ${user.name.split(" ")[0]}`} description="Your interviews and pending feedback." /><InterviewerHome /></div>);
  }
  const exportMenu = can("reports.export") && (
    <DropdownMenu>
      <DropdownMenuTrigger asChild><Button variant="outline" data-testid="dashboard-export"><Download className="h-4 w-4" />Export</Button></DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => exp("summary", { period: "monthly" })}>Monthly summary</DropdownMenuItem>
        <DropdownMenuItem onClick={() => exp("funnel")}>Funnel</DropdownMenuItem>
        <DropdownMenuItem onClick={() => exp("recruiters")}>Recruiter performance</DropdownMenuItem>
        <DropdownMenuItem onClick={() => exp("sources")}>Sources</DropdownMenuItem>
        {can("cost.view") && <DropdownMenuItem onClick={() => exp("cost-per-hire")}>Cost per hire</DropdownMenuItem>}
        <DropdownMenuItem onClick={() => exp("age-per-hire")}>Age per hire</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
  const p = d?.period;
  return (
    <div data-testid="dashboard">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-[28px] font-semibold leading-tight tracking-[-0.02em] sm:text-[30px]" data-testid="page-title">Dashboard</h1>
          <p className="mt-1 text-[14px] text-subtle">
            Recruitment overview and key hiring metrics{p && <> · {fmtDate(p.start)} – {fmtDate(p.end)}<span className="hidden md:inline">, compared with {fmtDate(p.previous_start)} – {fmtDate(p.previous_end)}</span></>}
          </p>
        </div>
        {dual && <Pills label="View" value={view} options={[["overview", "Overview"], ["interviews", "My interviews"]]} onChange={setView} testid="dashboard-view" />}
        {!(dual && view === "interviews") && <Filters f={f} setF={setF} reqs={reqs} exportMenu={exportMenu} />}
      </div>
      {dual && view === "interviews" ? <InterviewerHome /> : !customReady ? <Unavailable className="min-h-[200px]">Choose a start and end date for the custom range</Unavailable>
        : !d ? <PageLoader label="Loading your dashboard" /> : (
          <div className={cn("space-y-4 transition-opacity", loading && "opacity-60")} data-testid="bento-grid">
            <KpiRow d={d} />
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
              <TrendTile d={d} gran={g} setGran={setGran} />
              <FunnelTile d={d} />
              {d.cost && <CostTile c={d.cost} gran={g} />}
              <AgeTile a={d.age_per_hire} gran={g} />
              <SourcesTile s={d.sources} />
              <RecruitersTile r={d.recruiters} showCost={!!d.cost} />
              <RequisitionsTile q={d.requisitions} rf={rf} setRf={setRf} />
              <UpcomingTile items={d.upcoming_interviews} />
              <ActivityTile items={d.activity} />
              <PendingTile items={d.pending} />
              <DistributionTile items={d.distribution} total={d.total_applications} />
            </div>
            <p className="flex items-center gap-1.5 text-[12px] text-subtle"><CalendarClock className="h-3.5 w-3.5" />Figures come from portal records you have access to. "—" means there is no earlier data to compare with.</p>
          </div>)}
    </div>
  );
}
