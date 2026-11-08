import { Ban, Briefcase, CalendarDays, CheckCircle2, Clock3, FileText, FileX, Hourglass, IndianRupee, LayoutList, UserCheck, UserX, Users, XCircle } from "lucide-react";
import { Kpi } from "@/components/common/Page";
import { lakhs, num } from "@/lib/api";
import { AXIS, BRAND, SERIES_COLORS, STATUS } from "@/lib/brand";

export const COLORS = SERIES_COLORS;  // deep → royal → brand → sky → grey; green / amber only for outcomes
export const axis = AXIS;

export function KpiGrid({ k, cost, cycle, aph }) {
  const items = [
    ["Open Requisitions", k.open_requisitions, Briefcase], ["Open Positions", k.open_positions, LayoutList], ["Total Candidates", k.total_candidates, Users],
    ["In Process", k.in_process, Hourglass], ["Interviews Scheduled", k.interviews_scheduled, CalendarDays], ["Offers Released", k.offers_released, FileText],
    ["Offers Accepted", k.offers_accepted, CheckCircle2], ["Candidates Joined", k.joined, UserCheck], ["CV Rejections", k.cv_rejections, UserX],
    ["Interview Rejections", k.interview_rejections, XCircle], ["Offer Declines", k.offer_declines, FileX], ["Offer Revocations", k.offer_revocations, Ban],
  ];
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
      {items.map(([l, v, ic]) => <Kpi key={l} label={l} value={v} icon={ic} testid={`kpi-${l.toLowerCase().replace(/ /g, "-")}`} />)}
      {cost !== undefined && <Kpi icon={IndianRupee} label="Cost per Hire" value={cost ? (cost.cost_per_hire === null ? "N/A" : lakhs(cost.cost_per_hire)) : "—"} hint="Avg of CTC + consulting + recruiter fees" testid="kpi-cost-per-hire" />}
      {aph && <Kpi icon={Clock3} label="Age per Hire" value={num(aph.completed.avg, " d")} hint={`Median ${num(aph.completed.median, " d")} · DOJ − CRF`} testid="kpi-aph-avg" />}
      {cycle && <Kpi icon={Clock3} label="Avg Cycle Time" value={num(cycle.completed.avg, " d")} hint={`From earlier of CRF / initiation · median ${num(cycle.completed.median, " d")}`} testid="kpi-cycle-time" />}
    </div>
  );
}

export function FunnelChart({ funnel }) {
  const max = Math.max(1, ...funnel.map((f) => f.count));
  return (
    <div className="space-y-2.5" data-testid="funnel-chart">
      {funnel.map((f, i) => (
        <div key={f.stage} className="grid grid-cols-[130px_1fr_90px] items-center gap-3 text-sm">
          <span className="truncate text-[13px] font-medium text-[#4B5361]">{f.stage}</span>
          <div className="h-7 rounded-[6px] bg-[#F1F4F8]"><div className="flex h-7 items-center rounded-[6px] px-2 text-[12px] font-semibold tabular-nums text-white transition-all" style={{ width: `${Math.max(4, (f.count / max) * 100)}%`, background: i === funnel.length - 1 ? STATUS.positive : [BRAND.deep, BRAND.deep, BRAND.royal, BRAND.royal, BRAND.blue, BRAND.blue, BRAND.blue][Math.min(i, 6)] }}>{f.count}</div></div>
          <span className="text-right text-[11px] text-subtle">{i === 0 ? "—" : f.conversion === null ? "N/A" : `${f.conversion}% conv.`}</span>
        </div>
      ))}
    </div>
  );
}

