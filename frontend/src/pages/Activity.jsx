import { useState } from "react";
import { useFetch } from "@/lib/useFetch";
import { PageHeader } from "@/components/common/Page";
import { DataTable } from "@/components/common/DataTable";
import { SelectField } from "@/components/common/FormDialog";
import { fmtDateTime } from "@/lib/api";

const ENTITIES = ["requisition", "candidate", "application", "cost", "user", "master", "settings", "import", "report"];

export default function Activity() {
  const [f, setF] = useState({});
  const { data, loading } = useFetch("/activity", f);
  return (
    <div>
      <PageHeader eyebrow="Administration" title="Activity Log" description="Every create, update, status transition, interview, offer, joining and cost change — with user and timestamp." />
      <DataTable testid="activity-table" data={data} loading={loading} pageSize={20}
        toolbar={<>
          <SelectField value={f.entity} onChange={(v) => setF({ ...f, entity: v })} options={ENTITIES.map((e) => ({ value: e, label: e }))} placeholder="All records" testid="activity-filter-entity" className="w-40" />
          <input type="date" className="h-9 rounded-md border px-2 text-xs" value={f.date_from || ""} onChange={(e) => setF({ ...f, date_from: e.target.value })} data-testid="activity-filter-from" />
          <input type="date" className="h-9 rounded-md border px-2 text-xs" value={f.date_to || ""} onChange={(e) => setF({ ...f, date_to: e.target.value })} data-testid="activity-filter-to" />
        </>}
        columns={[{ key: "at", label: "When", render: (a) => <span className="whitespace-nowrap text-xs">{fmtDateTime(a.at)}</span> }, { key: "user_name", label: "User" },
          { key: "action", label: "Action", render: (a) => <span className="font-mono text-[11px]">{a.action}</span> }, { key: "entity", label: "Record type" },
          { key: "label", label: "Record", render: (a) => <span className="font-medium text-ink">{a.label}</span> }, { key: "details", label: "Details", className: "text-xs max-w-md" }]} />
    </div>
  );
}
