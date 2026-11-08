import { cn } from "@/lib/utils";

const TONES = {
  green: "bg-emerald-50 text-emerald-800 border-emerald-200 [&>i]:bg-emerald-500",
  amber: "bg-amber-50 text-amber-800 border-amber-200 [&>i]:bg-amber-500",
  rose: "bg-rose-50 text-rose-800 border-rose-200 [&>i]:bg-rose-500",
  plum: "bg-stone-100 text-stone-700 border-stone-300 [&>i]:bg-stone-500",
  zinc: "bg-zinc-100 text-zinc-700 border-zinc-200 [&>i]:bg-zinc-400",
  orange: "bg-orange-50 text-orange-800 border-orange-200 [&>i]:bg-orange-500",
  dark: "bg-[#18181B] text-white border-[#18181B] [&>i]:bg-white",
};

const MAP = {
  green: ["Joined", "Offer Accepted", "Accepted", "Approved", "Open", "Completed", "Complete", "Selected", "Paid", "Active", "Strong Hire", "Hire", "Joining Confirmed", "valid"],
  amber: ["Screening", "Shortlisted", "Interview Scheduled", "Interview In Progress", "Interview Completed", "Pending", "Scheduled", "Rescheduled", "Partial", "Partially Paid", "Hold", "Joining Deferred", "duplicate", "Imported"],
  plum: ["Offer Approval Pending", "Offer Released", "Approval Pending", "Released", "Not Submitted"],
  rose: ["CV Rejected", "Interview Rejected", "Candidate Withdrawn", "Offer Declined", "Offer Revoked", "No Show", "Declined", "Revoked", "Expired", "Cancelled", "Rejected", "Reject", "Inactive", "error"],
  zinc: ["New", "Draft", "On Hold", "Closed"],
  orange: ["Critical", "High"],
};
const toneOf = (s) => Object.keys(MAP).find((k) => MAP[k].includes(s)) || "zinc";

export function StatusBadge({ status, tone, className, testid }) {
  if (!status) return <span className="text-zinc-400">—</span>;
  return (
    <span data-testid={testid} className={cn("inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-semibold", TONES[tone || toneOf(status)], className)}>
      <i className="h-1.5 w-1.5 rounded-full" />
      {status}
    </span>
  );
}
