import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/AuthContext";
import { Info, PageHeader, Section } from "@/components/common/Page";
import { api, errMsg, fmtDateTime } from "@/lib/api";
import { toast } from "sonner";

export default function Profile() {
  const { user, setUser } = useAuth();
  const [p, setP] = useState({ name: user.name, phone: user.phone || "", designation: user.designation || "" });
  const [pw, setPw] = useState({ current_password: "", new_password: "", confirm: "" });
  const [busy, setBusy] = useState(null);
  const saveProfile = async () => {
    setBusy("p");
    try { const r = await api.put("/auth/profile", p); setUser(r.data); toast.success("Profile updated"); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(null); }
  };
  const changePw = async () => {
    if (pw.new_password !== pw.confirm) return toast.error("New passwords do not match");
    if (pw.new_password.length < 8) return toast.error("Password must be at least 8 characters");
    setBusy("w");
    try { await api.post("/auth/change-password", pw); setUser({ ...user, must_change_password: false }); setPw({ current_password: "", new_password: "", confirm: "" }); toast.success("Password changed"); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(null); }
  };
  const f = (obj, set, k, l, type = "text") => <div className="space-y-1"><Label className="text-xs">{l}</Label><Input type={type} value={obj[k]} onChange={(e) => set({ ...obj, [k]: e.target.value })} data-testid={`profile-${k}`} /></div>;
  return (
    <div>
      <PageHeader eyebrow="Account" title="My Profile" />
      {user.must_change_password && <p className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900" data-testid="must-change-password">You are using a temporary password. Please set a new one below.</p>}
      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Profile">
          <div className="mb-4 grid grid-cols-2 gap-4"><Info label="Email">{user.email}</Info><Info label="Role">{user.role_label}</Info><Info label="Last sign-in">{fmtDateTime(user.last_login)}</Info></div>
          <div className="space-y-3">{f(p, setP, "name", "Full name")}{f(p, setP, "designation", "Designation")}{f(p, setP, "phone", "Phone")}
            <Button onClick={saveProfile} disabled={busy === "p"} data-testid="profile-save">{busy === "p" && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Save profile</Button></div>
        </Section>
        <Section title="Change password">
          <div className="space-y-3">{f(pw, setPw, "current_password", "Current password", "password")}{f(pw, setPw, "new_password", "New password (min 8)", "password")}{f(pw, setPw, "confirm", "Confirm new password", "password")}
            <Button onClick={changePw} disabled={busy === "w"} data-testid="password-save">{busy === "w" && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Change password</Button></div>
        </Section>
      </div>
    </div>
  );
}
