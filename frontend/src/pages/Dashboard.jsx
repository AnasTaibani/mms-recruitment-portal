import { useState } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from "recharts";
import { useAuth } from "@/context/AuthContext";
import { useFetch } from "@/lib/useFetch";
import { Kpi, PageHeader, Section } from "@/components/common/Page";
import { StatusBadge } from "@/components/common/StatusBadge";
import { EmptyState } from "@/components/common/DataTable";
import { fmtDate, lakhs, num } from "@/lib/api";
import { APH_FORMULA, AphFilters, AphKpis, AphTrend } from "@/components/AgePerHire";

export const COLORS = ["#1E63CE", "#67B3F2", "#0B1530", "#3C86E8", "#A3D3FA", "#059669", "#D97706", "#94A3B8"];
export const axis = { fontSize: 11, fill: "#71717A" };

export function KpiGrid({ k, cost, cycle, aph }) {
  const items = [
    ["Open Requisitions", k.open_requisitions], ["Open Positions", k.open_positions], ["Total Candidates", k.total_candidates],
    ["In Process", k.in_process], ["Interviews Scheduled", k.interviews_scheduled], ["Offers Released", k.offers_released],
    ["Offers Accepted", k.offers_accepted], ["Candidates Joined", k.joined], ["CV Rejections", k.cv_rejections],
    ["Interview Rejections", k.interview_rejections], ["Offer Declines", k.offer_declines], ["Offer Revocations", k.offer_revocations],
  ];
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
      {items.map(([l, v]) => <Kpi key={l} label={l} value={v} testid={`kpi-${l.toLowerCase().replace(/ /g, "-")}`} />)}
      {cost !== undefined && <Kpi label="Cost per Hire" value={cost ? (cost.cost_per_hire === null ? "N/A" : lakhs(cost.cost_per_hire)) : "—"} hint="Avg of CTC + consulting + recruiter fees" testid="kpi-cost-per-hire" />}
      {aph && <Kpi label="Age per Hire" value={num(aph.completed.avg, " d")} hint={`Median ${num(aph.completed.median, " d")} · DOJ − CRF`} testid="kpi-aph-avg" />}
      {cycle && <Kpi label="Avg Cycle Time" value={num(cycle.completed.avg, " d")} hint={`From earlier of CRF / initiation · median ${num(cycle.completed.median, " d")}`} testid="kpi-cycle-time" />}
    </div>
  );
}

export function FunnelChart({ funnel }) {
  const max = Math.max(1, ...funnel.map((f) => f.count));
  return (
    <div className="space-y-2.5" data-testid="funnel-chart">
      {funnel.map((f, i) => (
        <div key={f.stage} className="grid grid-cols-[130px_1fr_90px] items-center gap-3 text-sm">
          <span className="truncate text-xs font-medium text-zinc-600">{f.stage}</span>
          <div className="h-7 rounded bg-zinc-100"><div className="flex h-7 items-center rounded px-2 text-xs font-bold text-white transition-all" style={{ width: `${Math.max(4, (f.count / max) * 100)}%`, background: i === funnel.length - 1 ? "#059669" : "#1E63CE" }}>{f.count}</div></div>
          <span className="text-right text-[11px] text-zinc-500">{i === 0 ? "—" : f.conversion === null ? "N/A" : `${f.conversion}% conv.`}</span>
        </div>
      ))}
    </div>
  );
}

function InterviewerHome() {
  const { data } = useFetch("/interviews", { mine: "true" });
  const rows = data || [];
  const upcoming = rows.filter((i) => ["Scheduled", "Rescheduled"].includes(i.status));
  const pending = rows.filter((i) => i.my_pending?.length && i.status !== "Cancelled");
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Section title={`Upcoming interviews (${upcoming.length})`} testid="my-upcoming">
        {!upcoming.length ? <EmptyState title="No upcoming interviews" /> : upcoming.map((i) => (
          <div key={i.id} className="flex items-center justify-between border-b border-zinc-100 py-2.5 last:border-0">
            <div><p className="text-sm font-medium">{i.candidate_name}</p><p className="text-xs text-zinc-500">{i.round_name} · {i.requisition_title}</p></div>
            <p className="text-xs text-zinc-600">{fmtDate(i.date)} {i.start_time}</p>
          </div>))}
      </Section>
      <Section title={`Feedback pending (${pending.length})`} testid="my-pending-feedback" actions={<Link to="/interviews" className="text-xs underline">Open interviews</Link>}>
        {!pending.length ? <EmptyState title="Nothing pending" /> : pending.map((i) => (
          <div key={i.id} className="flex items-center justify-between border-b border-zinc-100 py-2.5 last:border-0">
            <p className="text-sm">{i.candidate_name} · <span className="text-zinc-500">{i.round_name}</span></p><StatusBadge status={i.status} />
          </div>))}
      </Section>
    </div>
  );
}

function AgePerHirePanel() {
  const [f, setF] = useState({});
  const { data, loading } = useFetch("/analytics", f);
  return (
    <Section title="Age per Hire — time to hire" testid="dashboard-aph" actions={<Link to="/analytics?tab=aph" className="text-xs underline">Full analysis</Link>}>
      <div className="mb-4"><AphFilters f={f} setF={setF} testid="dash-aph-filter" /></div>
      {!data ? <p className="text-sm text-zinc-400">{loading ? "Loading…" : ""}</p> : (
        <div className="grid gap-4 xl:grid-cols-[1.25fr_1fr]">
          <div className="space-y-3"><AphKpis aph={data.aph} /><p className="text-[11px] text-zinc-400">{APH_FORMULA}</p></div>
          <AphTrend aph={data.aph} />
        </div>)}
    </Section>
  );
}

export default function Dashboard() {
  const { user, can } = useAuth();
  const { data, loading } = useFetch("/analytics", {}, can("analytics.view"));
  const scopeNote = { management: "Organisation-wide, read-only — plus the interviews you are assigned to." }[user.role];
  // users who hold Management and Interviewer roles switch between the two views here
  const dual = can("analytics.view") && user.role === "management" && (user.roles || []).includes("interviewer");
  const [view, setView] = useState("overview");
  return (
    <div>
      <PageHeader eyebrow={`${user.role_label} workspace`} title={`Welcome, ${user.name.split(" ")[0]}`} description={scopeNote || "Live recruitment overview from portal records."} />
      {dual && (
        <div className="mb-4 inline-flex rounded-xl border border-zinc-200 bg-white p-1" role="tablist" data-testid="dashboard-view-switch">
          {[["overview", "Management overview"], ["interviews", "My interviews"]].map(([k, l]) => (
            <button key={k} type="button" role="tab" aria-selected={view === k} onClick={() => setView(k)} data-testid={`dashboard-view-${k}`}
              className={`rounded-lg px-3 py-1.5 text-sm ${view === k ? "bg-zinc-900 text-white" : "text-zinc-600 hover:bg-zinc-50"}`}>{l}</button>))}
        </div>
      )}
      {dual && view === "interviews" ? <InterviewerHome /> : !can("analytics.view") ? <InterviewerHome /> : loading || !data ? <p className="text-sm text-zinc-400">Loading dashboard…</p> : (
        <div className="space-y-6">
          <KpiGrid k={data.kpis} cost={can("cost.view") ? data.cost : undefined} />
          <AgePerHirePanel />
          <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
            <Section title="Recruitment funnel" testid="dashboard-funnel"><FunnelChart funnel={data.funnel} /></Section>
            <Section title="Applications by status" testid="dashboard-status">
              {!data.status_breakdown.length ? <EmptyState title="No applications yet" hint="Add candidates to requisitions or import the MMS workbook." /> : (
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={data.status_breakdown} layout="vertical" margin={{ left: 40 }}>
                    <CartesianGrid horizontal={false} stroke="#F4F4F5" /><XAxis type="number" tick={axis} allowDecimals={false} /><YAxis type="category" dataKey="status" tick={axis} width={130} />
                    <Tooltip /><Bar dataKey="count" radius={[0, 4, 4, 0]}>{data.status_breakdown.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Bar>
                  </BarChart>
                </ResponsiveContainer>)}
            </Section>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Section title="Monthly trend" testid="dashboard-trend">
              {!data.trends.length ? <EmptyState title="No trend data yet" /> : (
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={data.trends}><CartesianGrid stroke="#F4F4F5" /><XAxis dataKey="month" tick={axis} /><YAxis tick={axis} allowDecimals={false} /><Tooltip /><Legend wrapperStyle={{ fontSize: 11 }} />
                    <Line dataKey="applications" stroke="#1E63CE" strokeWidth={2} /><Line dataKey="offers" stroke="#D97706" strokeWidth={2} /><Line dataKey="joined" stroke="#059669" strokeWidth={2} /></LineChart>
                </ResponsiveContainer>)}
            </Section>
            <Section title="Open positions by role" testid="dashboard-roles" actions={<Link to="/requisitions" className="text-xs underline">All requisitions</Link>}>
              {!data.roles.filter((r) => r.status === "Open").length ? <EmptyState title="No open requisitions" /> : (
                <div className="space-y-2">{data.roles.filter((r) => r.status === "Open").slice(0, 8).map((r) => (
                  <Link key={r.id} to={`/requisitions/${r.id}`} className="flex items-center justify-between rounded-lg px-2 py-1.5 hover:bg-zinc-50">
                    <span className="text-sm"><span className="font-mono text-[11px] text-zinc-400">{r.code}</span> {r.title}</span>
                    <span className="text-xs text-zinc-600">{r.filled}/{r.positions} filled · {r.in_process} in process</span>
                  </Link>))}</div>)}
            </Section>
          </div>
          {can("interview.view") && user.role !== "management" && <InterviewerHome />}
        </div>
      )}
    </div>
  );
}
