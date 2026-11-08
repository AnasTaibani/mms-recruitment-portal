import { useState } from "react";
import { FileDown, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { PageHeader } from "@/components/common/Page";
import { Filters } from "@/pages/Analytics";
import { download, errMsg } from "@/lib/api";
import { toast } from "sonner";

const REPORTS = [
  ["candidates", "Candidate list", "cand.view"], ["requisitions", "Requisition-wise report", "req.view"], ["pipeline", "Application pipeline", "app.view"],
  ["interviews", "Interview schedule", "interview.view"], ["offers", "Offer report", "offer.view"], ["joinings", "Joining report", "joining.view"],
  ["costs", "Recruitment cost report (invoices)", "cost.view"], ["cost-per-hire", "Cost per hire report", "cost.view"], ["recruiters", "Recruiter-wise report", "analytics.view"], ["sources", "Source-wise report", "analytics.view"],
  ["funnel", "Funnel report", "analytics.view"], ["age-per-hire", "Age per Hire report", "analytics.view"], ["summary?period=monthly", "Monthly recruitment summary", "analytics.view"], ["summary?period=quarterly", "Quarterly recruitment summary", "analytics.view"],
];

export default function Reports() {
  const { can } = useAuth();
  const [f, setF] = useState({});
  const [busy, setBusy] = useState(null);
  const go = async (key, fmt) => {
    const [path, qs] = key.split("?");
    const extra = Object.fromEntries(new URLSearchParams(qs || ""));
    setBusy(key + fmt);
    try { await download(`/reports/${path}`, { ...f, ...extra, format: fmt }); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(null); }
  };
  return (
    <div>
      <PageHeader eyebrow="Insights" title="Reports & Export" description="Exports respect the filters below and your access permissions." />
      <Filters f={f} setF={setF} extra={false} />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {REPORTS.filter(([, , p]) => can(p)).map(([k, l]) => (
          <div key={k} className="flex items-center justify-between rounded-xl border border-zinc-200 bg-white p-4" data-testid={`report-${k.replace(/[?=]/g, "-")}`}>
            <div className="flex items-center gap-3"><FileDown className="h-5 w-5 text-zinc-400" /><p className="text-sm font-semibold text-zinc-900">{l}</p></div>
            <div className="flex gap-1.5">
              {["xlsx", "csv"].map((fmt) => <Button key={fmt} size="sm" variant={fmt === "xlsx" ? "default" : "outline"} disabled={!!busy} onClick={() => go(k, fmt)} data-testid={`report-${k.replace(/[?=]/g, "-")}-${fmt}`}>{busy === k + fmt ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : fmt.toUpperCase()}</Button>)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
