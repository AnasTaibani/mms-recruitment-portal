import { useState } from "react";
import { MoreHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuSub, DropdownMenuSubContent, DropdownMenuSubTrigger, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { useAuth } from "@/context/AuthContext";
import { MoveDialog, OfferDialog, ScheduleDialog, SelectionDialog } from "@/components/forms";
import { HireCostDialog } from "@/components/HireCost";

export const HM_ALLOWED = ["Shortlisted", "CV Rejected", "On Hold", "Interview Rejected", "Selected"];

export function useAllowedMoves() {
  const { meta, can } = useAuth();
  return (status) => {
    // offer decline / revoke are recorded through the offer itself, so they are not offered as plain moves
    const t = (meta.settings.transitions?.[status] || []).filter((s) => !["Offer Declined", "Offer Revoked"].includes(s));
    if (can("app.move")) return t;
    if (can("app.decide")) return t.filter((s) => HM_ALLOWED.includes(s));
    return [];
  };
}

export function AppActions({ app, onDone }) {
  const { can, meta } = useAuth();
  const allowed = useAllowedMoves()(app.status);
  const [move, setMove] = useState(null);
  const [dlg, setDlg] = useState(null);
  const any = allowed.length || can("interview.manage") || can("selection.decide") || can("offer.manage")
    || (can("cost.view") && ["Offer Accepted", "Joined"].includes(app.status));
  if (!any) return null;
  return (
    <div onClick={(e) => e.stopPropagation()}>
      <DropdownMenu>
        <DropdownMenuTrigger asChild><Button variant="ghost" size="icon" className="h-8 w-8" data-testid={`app-actions-${app.code}`}><MoreHorizontal className="h-4 w-4" /></Button></DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuLabel className="text-xs">{app.code}</DropdownMenuLabel>
          <DropdownMenuSeparator />
          {allowed.length > 0 && (
            <DropdownMenuSub>
              <DropdownMenuSubTrigger data-testid="app-action-move">Move stage</DropdownMenuSubTrigger>
              <DropdownMenuSubContent className="max-h-80 overflow-auto">
                {[...meta.pipeline, ...meta.terminal].filter((s) => allowed.includes(s)).map((s) => (
                  <DropdownMenuItem key={s} onClick={() => setMove({ app, status: s })} data-testid={`move-to-${s.toLowerCase().replace(/ /g, "-")}`}>{s}</DropdownMenuItem>
                ))}
              </DropdownMenuSubContent>
            </DropdownMenuSub>
          )}
          {can("interview.manage") && !app.closed && <DropdownMenuItem onClick={() => setDlg("schedule")} data-testid="app-action-schedule">Schedule interview</DropdownMenuItem>}
          {can("selection.decide") && !app.closed && <DropdownMenuItem onClick={() => setDlg("select")} data-testid="app-action-selection">Record selection decision</DropdownMenuItem>}
          {can("offer.manage") && ["Selected", "Offer Declined", "Offer Revoked"].includes(app.status) && <DropdownMenuItem onClick={() => setDlg("offer")} data-testid="app-action-offer">{app.status === "Selected" ? "Create offer" : "Create re-offer"}</DropdownMenuItem>}
          {can("cost.view") && ["Offer Accepted", "Joined"].includes(app.status) && <DropdownMenuItem onClick={() => setDlg("cost")} data-testid="app-action-cost">Recruitment cost{app.hire_cost ? ` · ₹${app.hire_cost.total} L` : " · not confirmed"}</DropdownMenuItem>}
        </DropdownMenuContent>
      </DropdownMenu>
      <MoveDialog move={move} onClose={() => setMove(null)} onDone={onDone} />
      <ScheduleDialog open={dlg === "schedule"} onOpenChange={(o) => !o && setDlg(null)} application={app} onDone={onDone} />
      <SelectionDialog open={dlg === "select"} onOpenChange={(o) => !o && setDlg(null)} app={app} onDone={onDone} />
      <HireCostDialog app={app} open={dlg === "cost"} onOpenChange={(o) => !o && setDlg(null)} onDone={onDone} />
      <OfferDialog open={dlg === "offer"} onOpenChange={(o) => !o && setDlg(null)} app={app} onDone={onDone} />
    </div>
  );
}
