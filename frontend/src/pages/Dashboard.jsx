import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AlertTriangle, ArrowUpRight, CalendarClock, ChevronRight, Download, Loader2 } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useFetch } from "@/lib/useFetch";
import { PageHeader } from "@/components/common/Page";
import { StatusBadge } from "@/components/common/StatusBadge";
import { SelectField } from "@/components/common/FormDialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { CountUp, ChartTip, Delta, EASE, Pills, SegBar, SERIES, TONE, Tile, Unavailable, bucketLabel, useMounted } from "@/components/bento";
import { download, fmtDate, fmtDateTime } from "@/lib/api";
import { cn } from "@/lib/utils";

const PERIODS = [["7d", "7D"], ["30d", "30D"], ["90d", "90D"], ["quarter", "Quarter"], ["year", "Year"], ["custom", "Custom"]];
const axis = { fontSize: 11, fill: "#A1A1AA", fontFamily: "JetBrains Mono, monospace" };
const STAGE_TONE = { Joined: TONE.up, "CV Rejected": TONE.down, "Interview Rejected": TONE.down, "Candidate Withdrawn": "#C9A9A4",
  "Offer Declined": "#C9A9A4", "Offer Revoked": "#C9A9A4", "No Show": "#C9A9A4", "On Hold": TONE.warn };
const greys = ["#18181B", "#3F3F46", "#57534E", "#78716C", "#A8A29E", "#C7C3BF", "#D6D3D1", "#E7E5E4"];
const lk = (v) => (v == null ? "—" : `₹${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2 })} L`);
const linkCls = "text-xs text-zinc-500 underline-offset-2 hover:text-[#18181B] hover:underline";

/* Interviewer view (also "My interviews" for Management members) */
function InterviewerHome() {
  const { data } = useFetch("/interviews", { mine: "true" });
  const rows = data || [];
  const upcoming = rows.filter((i) => ["Scheduled", "Rescheduled"].includes(i.status));
  const pending = rows.filter((i) => i.my_pending?.length && i.status !== "Cancelled");
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <Tile title={`Upcoming interviews · ${upcoming.length}`} testid="my-upcoming">
        {!upcoming.length ? <Unavailable>No upcoming interviews</Unavailable> : upcoming.map((i) => (
          <Link to="/interviews" key={i.id} className="flex items-center justify-between gap-3 rounded-2xl px-2 py-2.5 transition-colors hover:bg-[#F5F5F4]">
            <div className="min-w-0"><p className="truncate text-sm font-medium">{i.candidate_name}</p><p className="truncate text-xs text-zinc-500">{i.round_name} · {i.requisition_title}</p></div>
            <p className="shrink-0 font-mono text-[11px] text-zinc-600">{fmtDate(i.date)} {i.start_time}</p>
          </Link>))}
      </Tile>
      <Tile title={`Feedback pending · ${pending.length}`} testid="my-pending-feedback" action={<Link to="/interviews" className={linkCls}>Open interviews</Link>}>
        {!pending.length ? <Unavailable>Nothing pending</Unavailable> : pending.map((i) => (
          <Link to="/interviews" key={i.id} className="flex items-center justify-between gap-3 rounded-2xl px-2 py-2.5 hover:bg-[#F5F5F4]">
            <p className="min-w-0 truncate text-sm">{i.candidate_name} · <span className="text-zinc-500">{i.round_name}</span></p><StatusBadge status={i.status} />
          </Link>))}
      </Tile>
    </div>
  );
}

function FilterBar({ f, setF, reqs, exportMenu }) {
  const { list } = useAuth();
  const m = (t) => list(t).map((x) => ({ value: x.id, label: x.name }));
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2" data-testid="dashboard-filters">
      <Pills label="Period" value={f.period} options={PERIODS} onChange={(v) => setF({ ...f, period: v })} testid="period" size="md" />
      {f.period === "custom" && (
        <span className="flex flex-wrap items-center gap-1.5">
          <Input type="date" className="h-9 w-[150px] rounded-full bg-white text-xs" value={f.date_from || ""} max={f.date_to || undefined} onChange={(e) => setF({ ...f, date_from: e.target.value })} data-testid="period-from" />
          <span className="text-xs text-zinc-400">to</span>
          <Input type="date" className="h-9 w-[150px] rounded-full bg-white text-xs" value={f.date_to || ""} min={f.date_from || undefined} onChange={(e) => setF({ ...f, date_to: e.target.value })} data-testid="period-to" />
        </span>
      )}
      <div className="flex flex-wrap items-center gap-2 lg:ml-auto">
        <SelectField value={f.department_id} onChange={(v) => setF({ ...f, department_id: v })} options={m("department")} placeholder="All departments" testid="dash-filter-department" className="h-9 w-40 rounded-full bg-white" />
        <SelectField value={f.recruiter_id} onChange={(v) => setF({ ...f, recruiter_id: v })} options={m("recruiter")} placeholder="All recruiters" testid="dash-filter-recruiter" className="h-9 w-40 rounded-full bg-white" />
        <SelectField value={f.requisition_id} onChange={(v) => setF({ ...f, requisition_id: v })} options={(reqs || []).map((r) => ({ value: r.id, label: `${r.code} · ${r.title}` }))} placeholder="All requisitions" testid="dash-filter-requisition" className="h-9 w-48 rounded-full bg-white" />
        {exportMenu}
      </div>
    </div>
  );
}

function Hero({ d, user }) {
  const lead = d.hero.find((h) => h.key === "hires");
  const rest = d.hero.filter((h) => h.key !== "hires");
  const p = d.period;
  const hour = new Date().getHours();
  return (
    <Tile className="sm:col-span-2 lg:col-span-4" testid="dashboard-hero">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,2fr)]">
        <div className="flex min-w-0 flex-col justify-between gap-6">
          <div>
            <p className="text-[26px] font-semibold leading-[1.1] tracking-[-0.03em] sm:text-[32px]">Good {hour < 12 ? "morning" : hour < 17 ? "afternoon" : "evening"}, {user.name.split(" ")[0]}</p>
            <p className="mt-1.5 text-sm text-zinc-500">{fmtDate(p.start)} – {fmtDate(p.end)} <span className="text-zinc-400">· compared with {fmtDate(p.previous_start)} – {fmtDate(p.previous_end)}</span></p>
          </div>
          <Link to={lead.link} className="group/lead block rounded-[20px] bg-[#18181B] p-5 text-white transition-transform duration-300 hover:-translate-y-0.5" data-testid="hero-hires">
            <div className="flex items-center justify-between">
              <p className="text-[12px] text-zinc-400">{lead.label} in period</p>
              <ArrowUpRight className="h-4 w-4 text-zinc-500 transition group-hover/lead:text-white" />
            </div>
            <p className="mt-2 font-mono text-[48px] font-semibold leading-none tracking-[-0.05em]"><CountUp value={lead.value} testid="hero-hires-value" /></p>
            <p className="mt-2 flex flex-wrap items-center gap-2 font-mono text-[11px] text-zinc-400">
              <span>prev. {lead.previous_count}</span>
              {lead.change_pct === null ? <span>· no earlier data to compare</span>
                : <span style={{ color: lead.change_pct >= 0 ? "#9FD3B4" : "#E8A39C" }}>{lead.change_pct >= 0 ? "▲" : "▼"} {Math.abs(lead.change_pct).toFixed(1)}%</span>}
              <span>· {lead.all_time} currently joined</span>
            </p>
          </Link>
        </div>
        <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
          {rest.map((h) => (
            <Link key={h.key} to={h.link} data-testid={`hero-${h.key}`}
              className="group/k flex min-w-0 flex-col justify-between rounded-[18px] border border-[#EFEDEA] bg-[#FAFAF9] p-4 transition-all duration-300 hover:-translate-y-0.5 hover:border-[#D6D3D1] hover:bg-white">
              <div className="flex items-start justify-between gap-2">
                <p className="text-[12px] text-zinc-500">{h.label}</p>
                <ArrowUpRight className="h-3.5 w-3.5 shrink-0 text-zinc-300 transition group-hover/k:text-zinc-700" />
              </div>
              <p className="mt-3 font-mono text-[30px] font-semibold leading-none tracking-[-0.04em]"><CountUp value={h.value} testid={`hero-${h.key}-value`} /></p>
              <p className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px] text-zinc-500">
                <span className="font-mono tabular-nums">{h.flow ? `prev. ${h.previous_count}` : `${h.period_count} ${h.note}`}</span>
                <Delta pct={h.change_pct} />
              </p>
            </Link>
          ))}
        </div>
      </div>
    </Tile>
  );
}

function TrendTile({ d, gran, setGran }) {
  const series = d.trend.series;
  const [hidden, setHidden] = useState({});
  const pts = d.trend.points;
  const empty = !pts.some((p) => series.some((s) => p[s.key] > 0));
  const totals = Object.fromEntries(series.map((s) => [s.key, pts.reduce((t, p) => t + p[s.key], 0)]));
  return (
    <Tile title="Recruitment performance" className="sm:col-span-2 lg:col-span-3 lg:row-span-2" testid="dashboard-trend"
      action={<Pills label="Granularity" value={gran} options={[["week", "Weekly"], ["month", "Monthly"]]} onChange={setGran} testid="granularity" />}>
      <div className="mb-3 flex flex-wrap gap-x-6 gap-y-2" role="group" aria-label="Series — click to show or hide">
        {series.map((s) => (
          <button key={s.key} type="button" onClick={() => setHidden({ ...hidden, [s.key]: !hidden[s.key] })} aria-pressed={!hidden[s.key]} data-testid={`trend-toggle-${s.key}`}
            className={cn("rounded-lg text-left transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400", hidden[s.key] && "opacity-35")}>
            <span className="flex items-center gap-1.5 text-[11.5px] text-zinc-500"><i className="h-[3px] w-3.5 rounded-full" style={{ background: SERIES[s.key] }} />{s.label}</span>
            <span className="font-mono text-[18px] font-semibold tabular-nums">{totals[s.key]}</span>
          </button>
        ))}
      </div>
      {empty ? <Unavailable className="min-h-[260px]">No recruitment activity recorded in this period</Unavailable> : (
        <div className="relative min-h-[280px] flex-1" data-testid="trend-chart">
          <ResponsiveContainer width="100%" height="100%" minHeight={280}>
            <AreaChart data={pts} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <defs>
                {series.map((s) => (
                  <linearGradient key={s.key} id={`g-${s.key}`} x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0" stopColor={SERIES[s.key]} stopOpacity={s.key === "added" ? 0.14 : 0.06} />
                    <stop offset="1" stopColor={SERIES[s.key]} stopOpacity={0} />
                  </linearGradient>))}
              </defs>
              <CartesianGrid vertical={false} stroke="#F0EFEC" strokeDasharray="2 6" />
              <XAxis dataKey="bucket" tick={axis} tickLine={false} axisLine={false} tickFormatter={(k) => bucketLabel(k, gran)} minTickGap={18} />
              <YAxis tick={axis} tickLine={false} axisLine={false} allowDecimals={false} width={36} />
              <Tooltip cursor={{ stroke: "#D6D3D1", strokeWidth: 1 }} content={<ChartTip labelFormat={(k) => (gran === "week" ? `Week of ${bucketLabel(k, gran)}` : bucketLabel(k, gran))} />} />
              {series.filter((s) => !hidden[s.key]).map((s) => (
                <Area key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={SERIES[s.key]} strokeWidth={s.key === "added" ? 2.4 : 1.8}
                  strokeDasharray={s.key === "interviews_completed" ? "5 4" : undefined} fill={`url(#g-${s.key})`} dot={false}
                  activeDot={{ r: 4, strokeWidth: 2, stroke: "#fff" }} animationDuration={900} />))}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </Tile>
  );
}

function FunnelTile({ d }) {
  const nav = useNavigate();
  const mounted = useMounted();
  const st = d.funnel.stages;
  const max = Math.max(1, ...st.map((s) => s.count));
  return (
    <Tile title="Recruitment funnel" className="sm:col-span-2 lg:col-span-1 lg:row-span-2" testid="dashboard-funnel"
      action={<span className="font-mono text-[11px] text-zinc-500" title="Applications created in the period that reached Joined" data-testid="funnel-overall">{d.funnel.overall_conversion == null ? "—" : `${d.funnel.overall_conversion}%`} overall</span>}>
      {!d.funnel.cohort ? <Unavailable>No applications created in this period</Unavailable> : (
        <ol className="flex flex-1 flex-col justify-between gap-1.5">
          {st.map((s, i) => (
            <li key={s.stage}>
              <button type="button" onClick={() => nav(`/pipeline?status=${encodeURIComponent(s.statuses.join(","))}`)} data-testid={`funnel-stage-${s.stage.toLowerCase().replace(/ /g, "-")}`}
                className="group/f w-full rounded-xl px-1.5 py-1 text-left transition-colors hover:bg-[#F5F5F4] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400" title={`Open ${s.stage} in the pipeline`}>
                <span className="flex items-baseline justify-between gap-2 text-[12px]">
                  <span className="truncate text-zinc-600 group-hover/f:text-[#18181B]">{s.stage}</span>
                  <span className="font-mono font-semibold tabular-nums">{s.count}</span>
                </span>
                <span className="mt-1 block h-2 rounded-full bg-[#F0EFEC]">
                  <span className="block h-2 rounded-full" style={{ width: mounted ? `${Math.max(2, (s.count / max) * 100)}%` : "2%", background: i === st.length - 1 ? TONE.up : greys[Math.min(i, 5)], transition: `width 900ms ${EASE} ${i * 60}ms` }} />
                </span>
                {i > 0 && <span className="mt-0.5 flex justify-between font-mono text-[10px] tabular-nums text-zinc-400">
                  <span>{s.conversion == null ? "—" : `${s.conversion}% of previous`}</span><span>{s.drop_off ? `−${s.drop_off}` : ""}</span>
                </span>}
              </button>
            </li>
          ))}
        </ol>
      )}
      <p className="mt-3 text-[10.5px] leading-snug text-zinc-400">{d.funnel.cohort} application(s) created in the period · each stage counts applications that reached it</p>
    </Tile>
  );
}

function CostTile({ c, gran }) {
  const parts = [{ key: "ctc", label: "Candidate CTC", value: c.ctc_total }, { key: "consulting", label: "Consulting fees", value: c.consulting_total }, { key: "recruiter", label: "Recruiter fees", value: c.recruiter_total }];
  const pc = ["#18181B", "#78716C", "#C7C3BF"];
  const hasTrend = c.trend.filter((t) => t.avg != null).length >= 2;
  return (
    <Tile title="Cost per hire" className="sm:col-span-2 lg:col-span-2" testid="dashboard-cost" action={<Link to="/costs" className={linkCls}>Details</Link>}>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[12px] text-zinc-500">Average cost per hire</p>
          <p className="font-mono text-[36px] font-semibold leading-none tracking-[-0.04em]" data-testid="dash-cost-avg">{c.cost_per_hire == null ? "N/A" : <CountUp value={c.cost_per_hire} format={(v) => lk(Math.round(v * 100) / 100)} />}</p>
          <p className="mt-1.5 text-[11px] text-zinc-500">{c.hires} of {c.joined} joined hire(s) with confirmed cost</p>
        </div>
        <div className="text-right">
          <p className="text-[12px] text-zinc-500">Total recruitment cost</p>
          <p className="font-mono text-[22px] font-semibold tabular-nums" data-testid="dash-cost-total">{lk(c.total)}</p>
        </div>
      </div>
      {c.total > 0 && <div className="mt-4"><SegBar items={parts} height={12} colorOf={(_, i) => pc[i]} testid="cost-split" /></div>}
      <dl className="mt-3 grid grid-cols-3 gap-3">
        {parts.map((p, i) => (
          <div key={p.key} className="min-w-0">
            <dt className="flex items-center gap-1.5 text-[11px] text-zinc-500"><i className="h-2 w-2 shrink-0 rounded-full" style={{ background: pc[i] }} /><span className="truncate">{p.label}</span></dt>
            <dd className="mt-0.5 truncate font-mono text-[14px] font-semibold tabular-nums">{lk(p.value)}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-4 h-[96px]">
        {hasTrend ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={c.trend} margin={{ top: 6, right: 6, left: 6, bottom: 0 }}>
              <XAxis dataKey="bucket" hide />
              <Tooltip content={<ChartTip labelFormat={(k) => bucketLabel(k, gran)} valueFormat={(v, p) => `${lk(v)} · ${p.payload.hires} hire(s)`} />} />
              <Line type="monotone" dataKey="avg" name="Avg cost per hire" stroke="#18181B" strokeWidth={2} dot={{ r: 2.5, fill: "#18181B" }} connectNulls animationDuration={900} />
            </LineChart>
          </ResponsiveContainer>
        ) : <Unavailable className="h-full py-2">{c.trend.some((t) => t.avg != null) ? "Trend appears once two or more periods have confirmed costs" : "No confirmed hire costs in this period"}</Unavailable>}
      </div>
      {(c.unconfirmed > 0 || c.pending_confirmation > 0) && (
        <p className="mt-3 flex items-start gap-1.5 rounded-xl bg-[#FBF6EC] px-3 py-2 text-[11px] text-[#8A5A12]" data-testid="dash-cost-incomplete">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{c.unconfirmed > 0 && `${c.unconfirmed} joined hire(s) have no confirmed cost and are excluded. `}{c.pending_confirmation > 0 && `${c.pending_confirmation} accepted offer(s) await cost confirmation.`}</span>
        </p>)}
      <p className="mt-2 text-[10.5px] text-zinc-400">Cost per hire = Candidate CTC + Consulting fees + Recruiter fees</p>
    </Tile>
  );
}

function AgeTile({ a, gran }) {
  const c = a.completed;
  const hasTrend = a.trend.filter((t) => t.avg != null).length >= 2;
  return (
    <Tile title="Age per hire" className="sm:col-span-2 lg:col-span-2" testid="dashboard-aph" action={<Link to="/analytics?tab=aph" className={linkCls}>Full analysis</Link>}>
      <div className="grid grid-cols-3 gap-3">
        {[["Average", c.avg], ["Fastest", c.min], ["Longest", c.max]].map(([l, v], i) => (
          <div key={l} className="min-w-0">
            <p className="text-[12px] text-zinc-500">{l}</p>
            <p className={cn("font-mono font-semibold leading-none tracking-[-0.04em] tabular-nums", i === 0 ? "text-[36px]" : "mt-2 text-[22px]")} data-testid={`dash-aph-${l.toLowerCase()}`}>
              {v == null ? "—" : <CountUp value={v} format={(x) => (Number.isInteger(v) ? Math.round(x) : x.toFixed(1))} />}{v != null && <span className="ml-1 text-[13px] text-zinc-400">d</span>}
            </p>
          </div>
        ))}
      </div>
      <p className="mt-1.5 text-[11px] text-zinc-500">{c.count} hire(s) · Actual date of joining − CRF raised date, calendar days</p>
      <div className="mt-3 h-[84px]">
        {hasTrend ? (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={a.trend} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
              <XAxis dataKey="bucket" hide />
              <Tooltip cursor={{ fill: "#F5F5F4" }} content={<ChartTip labelFormat={(k) => bucketLabel(k, gran)} valueFormat={(v, p) => `${v} days · ${p.payload.hires} hire(s)`} />} />
              <Bar dataKey="avg" name="Avg age per hire" fill="#57534E" radius={[5, 5, 2, 2]} animationDuration={900} />
            </BarChart>
          </ResponsiveContainer>
        ) : <Unavailable className="h-full py-2">{a.trend.some((t) => t.avg != null) ? "Trend appears once two or more periods have hires" : "No completed hires with a CRF date in this period"}</Unavailable>}
      </div>
      {a.by_requisition.length > 0 && (
        <ul className="mt-3 space-y-1" data-testid="aph-by-requisition">
          {a.by_requisition.slice(0, 4).map((r) => (
            <li key={r.requisition} className="flex items-center justify-between gap-3 text-[12px]">
              <span className="min-w-0 truncate text-zinc-600"><span className="font-mono text-[11px] text-zinc-400">{r.requisition}</span> {r.role}</span>
              <span className="shrink-0 font-mono tabular-nums">{r.avg} d <span className="text-zinc-400">· {r.hires} hire(s)</span></span>
            </li>))}
        </ul>)}
      {(a.missing_crf.length > 0 || a.flagged > 0) && (
        <p className="mt-3 flex items-start gap-1.5 rounded-xl bg-[#FBF6EC] px-3 py-2 text-[11px] text-[#8A5A12]" data-testid="dash-aph-flags">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{a.missing_crf.length > 0 && `${a.missing_crf.length} open requisition(s) have no CRF raised date. `}{a.flagged > 0 && `${a.flagged} hire(s) excluded for missing or invalid dates.`}</span>
        </p>)}
    </Tile>
  );
}

function SourcesTile({ s }) {
  const nav = useNavigate();
  const go = (id) => id && nav(`/candidates?source_id=${id}`);
  return (
    <Tile title="Candidate sources" className="sm:col-span-2 lg:col-span-2" testid="dashboard-sources">
      {!s.length ? <Unavailable>No candidates in this period</Unavailable> : (
        <>
          <SegBar items={s.map((x) => ({ key: x.source, label: x.source, value: x.candidates, id: x.source_id }))} height={34} colorOf={(_, i) => greys[i % greys.length]} onSelect={(x) => go(x.id)} testid="source-bar" />
          <table className="mt-4 w-full text-[12.5px]">
            <thead><tr className="text-left text-[11px] text-zinc-400"><th className="pb-1.5 font-normal">Source</th><th className="pb-1.5 text-right font-normal">Candidates</th><th className="pb-1.5 text-right font-normal">Shortlisted</th><th className="pb-1.5 text-right font-normal">Hired</th></tr></thead>
            <tbody>
              {s.map((x, i) => (
                <tr key={x.source} onClick={() => go(x.source_id)} className={cn("border-t border-[#F0EFEC]", x.source_id && "cursor-pointer hover:bg-[#FAFAF9]")} data-testid={`source-row-${x.source}`}>
                  <td className="py-1.5"><span className="flex items-center gap-2"><i className="h-2 w-2 shrink-0 rounded-full" style={{ background: greys[i % greys.length] }} />{x.source}{x.source_id && <ChevronRight className="h-3 w-3 text-zinc-300" />}</span></td>
                  <td className="py-1.5 text-right font-mono tabular-nums">{x.candidates}</td>
                  <td className="py-1.5 text-right font-mono tabular-nums">{x.shortlisted}</td>
                  <td className="py-1.5 text-right font-mono tabular-nums">{x.joined}</td>
                </tr>))}
            </tbody>
          </table>
        </>)}
    </Tile>
  );
}

function RecruitersTile({ r, showCost }) {
  const nav = useNavigate();
  const [metric, setMetric] = useState("assigned");
  const opts = [["assigned", "Assigned"], ["screened", "Screened"], ["interviews", "Interviews"], ["offers_released", "Offers"], ["joined", "Joined"]];
  const data = r.slice(0, 8);
  return (
    <Tile title="Recruiter performance" className="sm:col-span-2 lg:col-span-2" testid="dashboard-recruiters"
      action={<Pills label="Metric" value={metric} options={opts} onChange={setMetric} testid="recruiter-metric" />}>
      {!data.length ? <Unavailable>No recruiter activity in this period</Unavailable> : (
        <>
          <div style={{ height: Math.max(90, data.length * 26) }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} layout="vertical" margin={{ top: 0, right: 12, left: 0, bottom: 0 }}>
                <XAxis type="number" hide allowDecimals={false} />
                <YAxis type="category" dataKey="name" width={118} tick={{ ...axis, fill: "#57534E" }} tickLine={false} axisLine={false} tickFormatter={(n) => (n.length > 15 ? `${n.slice(0, 14)}…` : n)} />
                <Tooltip cursor={{ fill: "#F5F5F4" }} content={<ChartTip />} />
                <Bar dataKey={metric} name={opts.find((o) => o[0] === metric)[1]} fill="#27272A" radius={[0, 6, 6, 0]} barSize={14} animationDuration={700}
                  onClick={(x) => { const id = x?.recruiter_id || x?.payload?.recruiter_id; if (id) nav(`/pipeline?recruiter_id=${id}`); }} cursor="pointer" />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="-mx-1 mt-3 overflow-x-auto">
            <table className="w-full min-w-[500px] text-[12px]">
              <thead><tr className="text-left text-[11px] text-zinc-400">{["Recruiter", "Assigned", "Screened", "Interviews", "Offers", "Joined", "Age/hire", ...(showCost ? ["Cost/hire"] : [])].map((h, i) => <th key={h} className={cn("px-1 pb-1.5 font-normal", i && "text-right")}>{h}</th>)}</tr></thead>
              <tbody>{data.map((x) => (
                <tr key={x.name} className="border-t border-[#F0EFEC]">
                  <td className="max-w-[130px] truncate px-1 py-1.5">{x.recruiter_id ? <Link to={`/pipeline?recruiter_id=${x.recruiter_id}`} className="hover:underline">{x.name}</Link> : x.name}</td>
                  {["assigned", "screened", "interviews", "offers_released", "joined"].map((k) => <td key={k} className="px-1 py-1.5 text-right font-mono tabular-nums">{x[k]}</td>)}
                  <td className="px-1 py-1.5 text-right font-mono tabular-nums">{x.avg_age_per_hire == null ? "—" : `${x.avg_age_per_hire} d`}</td>
                  {showCost && <td className="px-1 py-1.5 text-right font-mono tabular-nums">{x.cost_per_hire == null ? "—" : lk(x.cost_per_hire)}</td>}
                </tr>))}</tbody>
            </table>
          </div>
        </>)}
    </Tile>
  );
}

const ageColor = (b) => (b === "90+ days" ? TONE.down : b === "61–90 days" ? TONE.warn : b === "No CRF date" ? "#E7E5E4" : b === "31–60 days" ? "#A8A29E" : "#57534E");

function RequisitionsTile({ q, rf, setRf }) {
  const { list } = useAuth();
  const m = (t) => list(t).map((x) => ({ value: x.id, label: x.name }));
  const stats = [["Open", q.open, "/requisitions?status=Open"], ["Positions approved", q.positions], ["Filled", q.filled], ["Remaining", q.remaining],
    ["On hold", q.on_hold, "/requisitions?status=On Hold"], ["Avg time to fill", q.avg_time_to_fill == null ? null : `${q.avg_time_to_fill} d`]];
  return (
    <Tile title="Requisitions" className="sm:col-span-2 lg:col-span-2" testid="dashboard-requisitions">
      <div className="mb-3 flex flex-wrap gap-2">
        <SelectField value={rf.hiring_manager_id} onChange={(v) => setRf({ ...rf, hiring_manager_id: v })} options={m("hiring_manager")} placeholder="All hiring managers" testid="req-filter-hm" className="h-8 w-40 rounded-full text-xs" />
        <SelectField value={rf.location_id} onChange={(v) => setRf({ ...rf, location_id: v })} options={m("location")} placeholder="All locations" testid="req-filter-location" className="h-8 w-32 rounded-full text-xs" />
        <SelectField value={rf.req_status} onChange={(v) => setRf({ ...rf, req_status: v })} options={["Open", "On Hold", "Closed", "Filled", "Cancelled"].map((s) => ({ value: s, label: s }))} placeholder="All statuses" testid="req-filter-status" className="h-8 w-32 rounded-full text-xs" />
      </div>
      <dl className="grid grid-cols-3 gap-x-3 gap-y-3">
        {stats.map(([l, v, href]) => {
          const inner = <><dt className="text-[11px] text-zinc-500">{l}</dt><dd className="mt-0.5 font-mono text-[20px] font-semibold tabular-nums">{v == null ? "—" : v}</dd></>;
          return href ? <Link key={l} to={href} className="rounded-xl px-1 hover:bg-[#F5F5F4]" data-testid={`req-stat-${l.toLowerCase().replace(/ /g, "-")}`}>{inner}</Link> : <div key={l} className="px-1" data-testid={`req-stat-${l.toLowerCase().replace(/ /g, "-")}`}>{inner}</div>;
        })}
      </dl>
      <p className="mt-4 text-[11px] text-zinc-500">Open requisitions by age (today − CRF raised date)</p>
      <div className="mt-1.5"><SegBar items={q.ageing.map((x) => ({ key: x.bucket, label: x.bucket, value: x.count }))} height={12} colorOf={(x) => ageColor(x.key)} testid="req-ageing" /></div>
      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[10.5px] text-zinc-500">{q.ageing.filter((x) => x.count).map((x) => <span key={x.bucket} className="flex items-center gap-1"><i className="h-1.5 w-1.5 rounded-full" style={{ background: ageColor(x.bucket) }} />{x.bucket} · {x.count}</span>)}</div>
      {q.oldest.length > 0 && (
        <ul className="mt-3 divide-y divide-[#F0EFEC]">
          {q.oldest.slice(0, 4).map((r) => (
            <li key={r.id}><Link to={`/requisitions/${r.id}`} className="flex items-center justify-between gap-3 py-1.5 text-[12px] hover:text-[#18181B]">
              <span className="min-w-0 truncate text-zinc-600"><span className="font-mono text-[11px] text-zinc-400">{r.code}</span> {r.title}</span>
              <span className="flex shrink-0 items-center gap-2 font-mono tabular-nums text-zinc-500">{r.filled}/{r.positions}<span className={cn(r.age > 90 && "text-[#B4534B]")}>{r.age == null ? "no CRF" : `${r.age} d`}</span></span>
            </Link></li>))}
        </ul>)}
      <p className="mt-2 text-[10.5px] text-zinc-400">Time to fill = last joining − CRF raised date, for fully filled requisitions ({q.time_to_fill_count})</p>
    </Tile>
  );
}

function UpcomingTile({ items }) {
  return (
    <Tile title="Upcoming interviews" testid="dashboard-upcoming" action={<Link to="/interviews" className={linkCls}>All</Link>}>
      {!items.length ? <Unavailable>No interviews scheduled</Unavailable> : (
        <ul className="-mx-2 space-y-0.5">{items.map((i) => (
          <li key={i.id}><Link to="/interviews" className="flex gap-3 rounded-2xl px-2 py-2 transition-colors hover:bg-[#F5F5F4]">
            <span className={cn("flex w-11 shrink-0 flex-col items-center justify-center rounded-xl py-1 font-mono", i.today ? "bg-[#18181B] text-white" : "bg-[#F5F5F4] text-zinc-700")}>
              <span className="text-[9px] uppercase">{i.today ? "Today" : new Date(`${i.date}T00:00:00`).toLocaleDateString("en-IN", { month: "short" })}</span>
              <span className="text-[13px] font-semibold leading-none">{i.today ? (i.time || "—").slice(0, 5) : new Date(`${i.date}T00:00:00`).getDate()}</span>
            </span>
            <span className="min-w-0">
              <span className="block truncate text-[13px] font-medium">{i.candidate}</span>
              <span className="block truncate text-[11px] text-zinc-500">{i.round} · {i.requisition}</span>
              <span className="block truncate text-[11px] text-zinc-400">{i.interviewers.join(", ") || "No interviewer"}{!i.today && i.time ? ` · ${i.time}` : ""}</span>
            </span>
          </Link></li>))}
        </ul>)}
    </Tile>
  );
}

function PendingTile({ items }) {
  const total = items.reduce((s, x) => s + x.count, 0);
  return (
    <Tile title="Pending actions" testid="dashboard-pending" action={<span className="font-mono text-[11px] text-zinc-500">{total}</span>}>
      <ul className="-mx-2 space-y-0.5">{items.map((p) => (
        <li key={p.key}><Link to={p.link} data-testid={`pending-${p.key}`} className="flex items-center justify-between gap-3 rounded-2xl px-2 py-2.5 transition-colors hover:bg-[#F5F5F4]">
          <span className="text-[12.5px] text-zinc-700">{p.label}</span>
          <span className={cn("grid h-7 min-w-7 place-items-center rounded-full px-2 font-mono text-[12px] font-semibold tabular-nums", p.count ? "bg-[#18181B] text-white" : "bg-[#F5F5F4] text-zinc-400")}>{p.count}</span>
        </Link></li>))}
      </ul>
    </Tile>
  );
}

function ActivityTile({ items }) {
  const mounted = useMounted();
  return (
    <Tile title="Recent recruitment activity" className="sm:col-span-2 lg:col-span-2" testid="dashboard-activity">
      {!items.length ? <Unavailable>No recent activity</Unavailable> : (
        <ul className="-mx-2">{items.slice(0, 8).map((x, i) => (
          <li key={i} style={{ opacity: mounted ? 1 : 0, transform: mounted ? "none" : "translateY(6px)", transition: `opacity 450ms ease ${i * 40}ms, transform 450ms ${EASE} ${i * 40}ms` }}>
            <Link to={`/candidates/${x.candidate_id}`} className="flex items-center gap-3 rounded-2xl px-2 py-2 transition-colors hover:bg-[#F5F5F4]">
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-[#F5F5F4] text-[10px] font-semibold text-zinc-600">{x.event.split(" ").map((w) => w[0]).slice(0, 2).join("")}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px]"><b className="font-medium">{x.event}</b> · {x.candidate}</span>
                <span className="block truncate text-[11px] text-zinc-500">{x.requisition} · by {x.by}</span>
              </span>
              <span className="hidden shrink-0 font-mono text-[10.5px] text-zinc-400 sm:block">{fmtDateTime(x.at)}</span>
            </Link>
          </li>))}
        </ul>)}
    </Tile>
  );
}

function DistributionTile({ items, total }) {
  const nav = useNavigate();
  const colorAt = (status, i) => STAGE_TONE[status] || greys[Math.min(i, 6)];
  const activeCount = items.filter((x) => x.active).reduce((s, x) => s + x.count, 0);
  return (
    <Tile title="Pipeline distribution · current stage" className="sm:col-span-2 lg:col-span-2" testid="dashboard-distribution" action={<span className="font-mono text-[11px] text-zinc-500">{total} applications</span>}>
      {!items.length ? <Unavailable>No applications</Unavailable> : (
        <>
          <SegBar items={items.map((x) => ({ key: x.status, label: x.status, value: x.count }))} height={34} colorOf={(x) => colorAt(x.key, items.findIndex((y) => y.status === x.key))}
            onSelect={(x) => nav(`/pipeline?status=${encodeURIComponent(x.key)}`)} testid="distribution-bar" />
          <ul className="mt-4 grid grid-cols-2 gap-x-4 gap-y-1.5 sm:grid-cols-3">
            {items.map((x, i) => (
              <li key={x.status}><Link to={`/pipeline?status=${encodeURIComponent(x.status)}`} className="flex items-center justify-between gap-2 rounded-lg px-1 text-[12px] hover:bg-[#F5F5F4]">
                <span className="flex min-w-0 items-center gap-1.5 truncate"><i className="h-2 w-2 shrink-0 rounded-full" style={{ background: colorAt(x.status, i) }} />{x.status}</span>
                <span className="font-mono tabular-nums text-zinc-500">{x.count}</span>
              </Link></li>))}
          </ul>
          <p className="mt-3 text-[11px] text-zinc-500">{activeCount} active · {total - activeCount} closed</p>
        </>)}
    </Tile>
  );
}

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
    return (<div><PageHeader eyebrow={`${user.role_label} workspace`} title={`Welcome, ${user.name.split(" ")[0]}`} description="Your interviews and pending feedback." /><InterviewerHome /></div>);
  }
  const exportMenu = can("reports.export") && (
    <DropdownMenu>
      <DropdownMenuTrigger asChild><Button variant="outline" size="sm" className="h-9 rounded-full bg-white" data-testid="dashboard-export"><Download className="mr-1.5 h-3.5 w-3.5" />Export</Button></DropdownMenuTrigger>
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
  return (
    <div data-testid="dashboard">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow mb-1">{user.role_label} · recruitment overview</p>
          <h1 className="text-2xl font-semibold tracking-[-0.02em] sm:text-[30px]" data-testid="page-title">Dashboard</h1>
        </div>
        {dual && <Pills label="View" value={view} options={[["overview", "Management overview"], ["interviews", "My interviews"]]} onChange={setView} testid="dashboard-view" size="md" />}
      </div>
      {dual && view === "interviews" ? <InterviewerHome /> : (
        <>
          <FilterBar f={f} setF={setF} reqs={reqs} exportMenu={exportMenu} />
          {!customReady ? <Unavailable className="min-h-[200px]">Choose a start and end date for the custom range</Unavailable>
            : !d ? <div className="flex h-60 items-center justify-center text-sm text-zinc-400"><Loader2 className="mr-2 h-4 w-4 animate-spin" />Loading dashboard…</div> : (
              <div className={cn("grid grid-cols-1 gap-3 transition-opacity sm:grid-cols-2 lg:grid-cols-4", loading && "opacity-60")} data-testid="bento-grid">
                <Hero d={d} user={user} />
                <TrendTile d={d} gran={g} setGran={setGran} />
                <FunnelTile d={d} />
                {d.cost && <CostTile c={d.cost} gran={g} />}
                <AgeTile a={d.age_per_hire} gran={g} />
                <SourcesTile s={d.sources} />
                <RecruitersTile r={d.recruiters} showCost={!!d.cost} />
                <RequisitionsTile q={d.requisitions} rf={rf} setRf={setRf} />
                <UpcomingTile items={d.upcoming_interviews} />
                <PendingTile items={d.pending} />
                <ActivityTile items={d.activity} />
                <DistributionTile items={d.distribution} total={d.total_applications} />
              </div>)}
          {d && <p className="mt-4 flex items-center gap-1.5 text-[11px] text-zinc-400"><CalendarClock className="h-3.5 w-3.5" />All figures come from portal records you have access to. "—" means there is no earlier data to compare with.</p>}
        </>
      )}
    </div>
  );
}
