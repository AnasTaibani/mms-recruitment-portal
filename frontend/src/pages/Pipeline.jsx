import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, Download, KanbanSquare, Table2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { useFetch } from "@/lib/useFetch";
import { useUrlDefaults } from "@/lib/urlFilters";
import { PageHeader } from "@/components/common/Page";
import { DataTable } from "@/components/common/DataTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { SelectField } from "@/components/common/FormDialog";
import { AppActions, useAllowedMoves } from "@/components/AppActions";
import { MoveDialog } from "@/components/forms";
import { api, download, errMsg } from "@/lib/api";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

function Card({ a, onDone }) {
  return (
    <div draggable onDragStart={(e) => e.dataTransfer.setData("text/plain", a.id)} data-testid={`kanban-card-${a.code}`}
      className={cn("cursor-grab rounded-lg border bg-white p-3 shadow-[0_1px_0_rgba(0,0,0,0.03)] transition-shadow hover:shadow-md active:cursor-grabbing", a.stuck ? "border-amber-300" : "border-line")}>
      <div className="flex items-start justify-between gap-2">
        <Link to={`/candidates/${a.candidate_id}`} className="text-sm font-semibold text-ink hover:underline">{a.candidate_name}</Link>
        <AppActions app={a} onDone={onDone} />
      </div>
      <p className="truncate text-xs text-subtle">{a.requisition_title}</p>
      <div className="mt-2 flex items-center justify-between text-[11px] text-[#9AA2AE]">
        <span>{a.recruiter || "Unassigned"}</span>
        <span className={cn(a.stuck && "flex items-center gap-1 font-semibold text-amber-700")}>{a.stuck && <AlertTriangle className="h-3 w-3" />}{a.days_in_stage}d</span>
      </div>
    </div>
  );
}

function Board({ apps, reload }) {
  const { meta } = useAuth();
  const allowed = useAllowedMoves();
  const [move, setMove] = useState(null);
  const [over, setOver] = useState(null);
  const cols = [...meta.pipeline, ...meta.terminal];
  const drop = async (status, e) => {
    e.preventDefault(); setOver(null);
    const a = apps.find((x) => x.id === e.dataTransfer.getData("text/plain"));
    if (!a || a.status === status) return;
    if (!allowed(a.status).includes(status)) { toast.error(`Moving from ${a.status} to ${status} is not permitted`); return; }
    setMove({ app: a, status });  // terminal outcomes ask for a reason; pipeline stages open the stage-completion wizard
  };
  return (
    <div className="scroll-thin -mx-4 overflow-x-auto px-4 pb-4" data-testid="kanban-board">
      <div className="flex gap-3">
        {cols.map((s) => {
          const items = apps.filter((a) => a.status === s);
          const term = meta.terminal.includes(s);
          return (
            <div key={s} onDragOver={(e) => { e.preventDefault(); setOver(s); }} onDragLeave={() => setOver(null)} onDrop={(e) => drop(s, e)} data-testid={`kanban-col-${s.toLowerCase().replace(/ /g, "-")}`}
              className={cn("flex w-64 shrink-0 flex-col rounded-xl border p-2 transition-colors", term ? "border-line bg-[#EEF1F5]/60" : "border-line bg-canvas", over === s && "border-brand-deep bg-[#EEF1F5]")}>
              <div className="mb-2 flex items-center justify-between px-1.5 py-1">
                <StatusBadge status={s} /><span className="text-xs font-semibold text-subtle">{items.length}</span>
              </div>
              <div className="min-h-[120px] space-y-2">{items.map((a) => <Card key={a.id} a={a} onDone={reload} />)}</div>
            </div>
          );
        })}
      </div>
      <MoveDialog move={move} onClose={() => setMove(null)} onDone={reload} />
    </div>
  );
}

export default function Pipeline() {
  const { list, meta, can } = useAuth();
  const init = useUrlDefaults({ slim: "true" }, ["status", "recruiter_id", "requisition_id"]);
  const [f, setF] = useState(init);
  const [view, setView] = useState(init.status || init.recruiter_id ? "table" : "board");
  const { data, loading, reload } = useFetch("/applications", f);
  const { data: reqs } = useFetch("/requisitions");
  const m = (t) => list(t).map((x) => ({ value: x.id, label: x.name }));
  const apps = data || [];
  const sel = (k, opts, ph, w = "w-40") => <SelectField value={f[k]} onChange={(v) => setF({ ...f, [k]: v })} options={opts} placeholder={ph} testid={`pipe-filter-${k}`} className={w} />;
  const cols = [
    { key: "code", label: "App ID", render: (a) => <span className="font-mono text-xs">{a.code}</span> },
    { key: "candidate_name", label: "Candidate", render: (a) => <Link to={`/candidates/${a.candidate_id}`} className="font-medium hover:underline" onClick={(e) => e.stopPropagation()}>{a.candidate_name}</Link> },
    { key: "requisition_title", label: "Role" },
    { key: "department", label: "Department" },
    { key: "recruiter", label: "Recruiter" },
    { key: "source", label: "Source" },
    { key: "status", label: "Stage", render: (a) => <StatusBadge status={a.status} /> },
    { key: "days_in_stage", label: "Days in stage", render: (a) => <span className={a.stuck ? "font-semibold text-amber-700" : ""}>{a.days_in_stage}{a.stuck && " · stuck"}</span> },
    { key: "recruitment_age", label: "Recruitment age" },
    { key: "actions", label: "", sortable: false, render: (a) => <AppActions app={a} onDone={reload} /> },
  ];
  const stuck = apps.filter((a) => a.stuck).length;
  return (
    <div>
      <PageHeader eyebrow="Recruitment" title="Pipeline" description="Drag cards between stages. Rejections, withdrawals and holds require a reason."
        actions={<>
          {can("reports.export") && <Button variant="outline" onClick={() => download("/reports/pipeline", f)} data-testid="pipe-export-btn"><Download className="mr-2 h-4 w-4" />Export</Button>}
          <div className="flex rounded-lg border border-line bg-white p-0.5">
            <Button size="sm" variant={view === "board" ? "default" : "ghost"} onClick={() => setView("board")} data-testid="pipe-view-board"><KanbanSquare className="mr-1.5 h-4 w-4" />Board</Button>
            <Button size="sm" variant={view === "table" ? "default" : "ghost"} onClick={() => setView("table")} data-testid="pipe-view-table"><Table2 className="mr-1.5 h-4 w-4" />Table</Button>
          </div>
        </>} />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {sel("requisition_id", (reqs || []).map((r) => ({ value: r.id, label: `${r.code} ${r.title}` })), "All requisitions", "w-56")}
        {sel("recruiter_id", m("recruiter"), "All recruiters")}
        {sel("department_id", m("department"), "All departments")}
        {sel("source_id", m("source"), "All sources")}
        {sel("status", [...(f.status?.includes(",") ? [{ value: f.status, label: f.status.split(",").length === 3 && f.status.startsWith("Interview") ? "Interview stages" : f.status.replace(/,/g, " / ") }] : []),
          ...[...meta.pipeline, ...meta.terminal].map((s) => ({ value: s, label: s }))], "All stages")}
        {stuck > 0 && <span className="ml-auto flex items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800" data-testid="stuck-alert"><AlertTriangle className="h-3.5 w-3.5" />{stuck} stuck over {meta.settings.stale_days} days</span>}
      </div>
      {loading ? <p className="text-sm text-[#9AA2AE]">Loading pipeline…</p> : view === "board" ? <Board apps={apps} reload={reload} /> : <DataTable testid="pipe-table" columns={cols} data={apps} />}
    </div>
  );
}
