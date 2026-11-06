import { useState } from "react";
import { KeyRound, Pencil, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { useFetch } from "@/lib/useFetch";
import { PageHeader } from "@/components/common/Page";
import { DataTable } from "@/components/common/DataTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { FormDialog } from "@/components/common/FormDialog";
import { api, errMsg, fmtDateTime } from "@/lib/api";
import { toast } from "sonner";

const DESC = { super_admin: "Full system access", recruiter: "All recruitment operations", interviewer: "Assigned interviews & feedback only", management: "Read-only dashboards & reports" };

export default function UsersPage() {
  const { meta, can, user: me, reloadRef } = useAuth();
  const { data, loading, reload } = useFetch("/users");
  const [dlg, setDlg] = useState(null);
  const roles = Object.entries(meta.roles).filter(([k]) => k !== "super_admin" || can("users.super")).map(([value, label]) => ({ value, label: `${label} — ${DESC[value]}` }));
  const save = async (fn, msg) => { try { await fn(); toast.success(msg); setDlg(null); reload(); reloadRef(); } catch (e) { toast.error(errMsg(e)); } };
  const cols = [
    { key: "name", label: "Name", render: (u) => <span className="font-medium text-zinc-900">{u.name}</span> },
    { key: "email", label: "Email" },
    { key: "role_label", label: "Role" },
    { key: "designation", label: "Designation" },
    { key: "active", label: "Status", value: (u) => (u.active ? "Active" : "Inactive"), render: (u) => <StatusBadge status={u.active ? "Active" : "Inactive"} /> },
    { key: "last_login", label: "Last login", render: (u) => fmtDateTime(u.last_login) },
    { key: "actions", label: "", sortable: false, render: (u) => (u.role === "super_admin" && !can("users.super")) ? null : (
      <div className="flex gap-1">
        <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => setDlg({ kind: "edit", u })} data-testid={`user-edit-${u.email}`}><Pencil className="h-3.5 w-3.5" /></Button>
        <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => setDlg({ kind: "reset", u })} data-testid={`user-reset-${u.email}`}><KeyRound className="h-3.5 w-3.5" /></Button>
      </div>) },
  ];
  return (
    <div>
      <PageHeader eyebrow="Administration" title="Users & Roles" description="Create accounts, assign roles and activate or deactivate access. Recruiters and interviewers are linked to their master-data entry automatically."
        actions={<Button onClick={() => setDlg({ kind: "new" })} data-testid="user-new-btn"><Plus className="mr-2 h-4 w-4" />New user</Button>} />
      <DataTable testid="users-table" columns={cols} data={data} loading={loading} />
      <FormDialog open={dlg?.kind === "new"} onOpenChange={(o) => !o && setDlg(null)} title="Create user" testid="user-form" description="The user must change this temporary password after first sign-in."
        fields={[{ name: "name", label: "Full name", required: true }, { name: "email", label: "Email", type: "email", required: true }, { name: "role", label: "Role", type: "select", options: roles, required: true },
          { name: "password", label: "Temporary password (min 8)", required: true }, { name: "designation", label: "Designation" }, { name: "phone", label: "Phone" }]}
        onSubmit={(v) => save(() => api.post("/users", v), "User created")} />
      <FormDialog open={dlg?.kind === "edit"} onOpenChange={(o) => !o && setDlg(null)} title={`Edit ${dlg?.u?.name}`} testid="user-edit-form" initial={dlg?.u && { ...dlg.u, active: dlg.u.active ? "true" : "false" }}
        fields={[{ name: "name", label: "Full name", required: true }, { name: "role", label: "Role", type: "select", options: roles, required: true },
          { name: "active", label: "Account status", type: "select", options: [{ value: "true", label: "Active" }, { value: "false", label: "Deactivated" }], required: true, help: dlg?.u?.id === me.id ? "You cannot deactivate yourself." : "" },
          { name: "designation", label: "Designation" }, { name: "phone", label: "Phone" }]}
        onSubmit={(v) => save(() => api.put(`/users/${dlg.u.id}`, { ...v, active: v.active === "true" }), "User updated")} />
      <FormDialog open={dlg?.kind === "reset"} onOpenChange={(o) => !o && setDlg(null)} title={`Reset password · ${dlg?.u?.name}`} testid="user-reset-form" submitLabel="Set temporary password"
        fields={[{ name: "password", label: "New temporary password (min 8)", required: true }]}
        onSubmit={(v) => (v.password.length < 8 ? toast.error("Minimum 8 characters") : save(() => api.post(`/users/${dlg.u.id}/reset-password`, v), "Password reset"))} />
    </div>
  );
}
