import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Eye, EyeOff, Loader2, Lock, Mail } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { errMsg } from "@/lib/api";

export default function Login() {
  const { user, login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [forgot, setForgot] = useState(false);
  if (user) return <Navigate to="/" replace />;

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setError("");
    try { await login(email, password); nav("/"); } catch (err) { setError(errMsg(err)); } finally { setBusy(false); }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-gradient-to-br from-[#EEF5FF] via-white to-[#E3EFFD] p-4">
      {/* soft brand-blue shapes, echoing the butterfly mark */}
      <div className="pointer-events-none absolute -left-32 -top-32 h-[28rem] w-[28rem] rounded-full bg-[#67B3F2]/30 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-40 -right-24 h-[32rem] w-[32rem] rounded-full bg-[#1E63CE]/20 blur-3xl" />
      <div className="pointer-events-none absolute right-1/4 top-16 h-48 w-48 rounded-full bg-[#A3D3FA]/40 blur-2xl" />
      <div className="pointer-events-none absolute inset-0 opacity-[0.35]" style={{ backgroundImage: "radial-gradient(#1E63CE22 1px, transparent 1px)", backgroundSize: "22px 22px" }} />

      <div className="fade-up relative w-full max-w-md">
        <div className="overflow-hidden rounded-3xl border border-white/70 bg-white/80 shadow-[0_20px_60px_-15px_rgba(30,99,206,0.25)] backdrop-blur-xl">
          <div className="h-1.5 w-full bg-gradient-to-r from-[#A3D3FA] via-[#67B3F2] to-[#1E63CE]" />
          <div className="px-8 pb-8 pt-9 sm:px-10">
            <img src="/mms-logo.png" alt="MetaMorphoSys Technologies" className="mx-auto h-14 w-auto" />
            <div className="mt-7 text-center">
              <h1 className="text-2xl font-bold tracking-tight text-[#0B1530]">Recruitment Portal</h1>
              <p className="mt-1 text-sm text-zinc-500">Sign in to your account</p>
            </div>

            <form onSubmit={submit} className="mt-8 space-y-5" data-testid="login-form">
              <div className="space-y-1.5">
                <Label htmlFor="email" className="text-xs font-semibold text-zinc-700">Email</Label>
                <div className="relative">
                  <Mail className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
                  <Input id="email" type="email" autoComplete="email" placeholder="name@metamorphtech.com" value={email} onChange={(e) => setEmail(e.target.value)} required
                    className="h-12 rounded-xl border-zinc-200 bg-white pl-10 focus-visible:ring-[#1E63CE]/40" data-testid="login-email-input" />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="password" className="text-xs font-semibold text-zinc-700">Password</Label>
                <div className="relative">
                  <Lock className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
                  <Input id="password" type={showPw ? "text" : "password"} autoComplete="current-password" placeholder="••••••••" value={password} onChange={(e) => setPassword(e.target.value)} required
                    className="h-12 rounded-xl border-zinc-200 bg-white pl-10 pr-11 focus-visible:ring-[#1E63CE]/40" data-testid="login-password-input" />
                  <button type="button" onClick={() => setShowPw(!showPw)} className="absolute right-3 top-1/2 -translate-y-1/2 rounded-md p-1 text-zinc-400 hover:text-zinc-700" aria-label={showPw ? "Hide password" : "Show password"} data-testid="login-toggle-password">
                    {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              {error && <p className="rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-sm text-rose-700" data-testid="login-error">{error}</p>}

              <Button type="submit" disabled={busy} data-testid="login-submit-button"
                className="h-12 w-full rounded-xl bg-gradient-to-r from-[#1E63CE] to-[#3C86E8] text-sm font-semibold text-white shadow-lg shadow-[#1E63CE]/25 transition hover:brightness-110 hover:shadow-[#1E63CE]/40">
                {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Sign in
              </Button>
            </form>

            <div className="mt-5 text-center">
              <button type="button" className="text-xs font-medium text-[#1E63CE] hover:underline" onClick={() => setForgot(!forgot)} data-testid="forgot-password-link">Forgot password?</button>
              {forgot && <p className="mt-2 text-xs text-zinc-500" data-testid="forgot-password-info">Ask your Super Admin or HR Admin to reset it from Users & Roles.</p>}
            </div>
          </div>
        </div>
        <p className="mt-6 text-center text-[11px] text-zinc-400">© {new Date().getFullYear()} MetaMorphoSys Technologies</p>
      </div>
    </div>
  );
}