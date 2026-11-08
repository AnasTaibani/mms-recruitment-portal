import { cn } from "@/lib/utils";

const TONES = {
  // restrained semantic colours; offer stages use the brand blue
  green: "bg-[#EAF6EF] text-[#2F6E4C] border-[#CFE8DA] [&>i]:bg-[#3E8E63]",
  amber: "bg-[#FBF4E6] text-[#8A6420] border-[#F0DFBD] [&>i]:bg-[#C08A2E]",
  rose: "bg-[#FBEDEC] text-[#9E3B37] border-[#F1D2D0] [&>i]:bg-[#C0504D]",
  plum: "bg-brand-pale text-brand-deep border-[#CFE3FB] [&>i]:bg-brand-royal",
  zinc: "bg-[#F1F3F6] text-[#4B5361] border-line [&>i]:bg-[#AEB5BF]",
  orange: "bg-[#FCF1E7] text-[#9A5320] border-[#F3D8C0] [&>i]:bg-[#D2793A]",
  dark: "bg-brand-deep text-white border-brand-deep [&>i]:bg-white",
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
  if (!status) return <span className="text-[#9AA2AE]">—</span>;
  return (
    <span data-testid={testid} className={cn("inline-flex items-center gap-1.5 whitespace-nowrap rounded-[6px] border px-2 py-[1px] text-[12px] font-medium leading-5", TONES[tone || toneOf(status)], className)}>
      <i className="h-1.5 w-1.5 rounded-full" />
      {status}
    </span>
  );
}
