import { Kpi } from "@/components/common/Page";
import { lakhs, num } from "@/lib/api";

export const COLORS = ["#18181B", "#57534E", "#A8A29E", "#D6D3D1", "#3F7D58", "#B7791F", "#78716C", "#E7E5E4"];  // neutral palette; green / ochre only for outcomes
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
          <div className="h-7 rounded bg-zinc-100"><div className="flex h-7 items-center rounded px-2 text-xs font-bold text-white transition-all" style={{ width: `${Math.max(4, (f.count / max) * 100)}%`, background: i === funnel.length - 1 ? "#3F7D58" : "#27272A" }}>{f.count}</div></div>
          <span className="text-right text-[11px] text-zinc-500">{i === 0 ? "—" : f.conversion === null ? "N/A" : `${f.conversion}% conv.`}</span>
        </div>
      ))}
    </div>
  );
}

