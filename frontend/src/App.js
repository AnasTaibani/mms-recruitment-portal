import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import AppShell from "@/components/layout/AppShell";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Requisitions from "@/pages/Requisitions";
import RequisitionDetail from "@/pages/RequisitionDetail";
import Candidates from "@/pages/Candidates";
import CandidateDetail from "@/pages/CandidateDetail";
import Pipeline from "@/pages/Pipeline";
import Interviews from "@/pages/Interviews";
import Offers from "@/pages/Offers";
import Joining from "@/pages/Joining";
import Costs from "@/pages/Costs";
import Analytics from "@/pages/Analytics";
import Reports from "@/pages/Reports";
import ImportPage from "@/pages/Import";
import Activity from "@/pages/Activity";
import UsersPage from "@/pages/Users";
import SettingsPage from "@/pages/Settings";
import Profile from "@/pages/Profile";

function Guard({ perm, children }) {
  const { user, meta, can } = useAuth();
  if (user === null || (user && !meta)) return <div className="flex h-screen items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-[#9AA2AE]" /></div>;
  if (!user) return <Navigate to="/login" replace />;
  if (perm && !can(perm)) return <div className="py-20 text-center text-sm text-subtle" data-testid="no-access">You do not have access to this page.</div>;
  return children;
}

const P = (perm, el) => <Guard perm={perm}>{el}</Guard>;

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<Guard><AppShell /></Guard>}>
            <Route index element={<Dashboard />} />
            <Route path="requisitions" element={P("req.view", <Requisitions />)} />
            <Route path="requisitions/:id" element={P("req.view", <RequisitionDetail />)} />
            <Route path="candidates" element={P("cand.view", <Candidates />)} />
            <Route path="candidates/:id" element={P("cand.view", <CandidateDetail />)} />
            <Route path="pipeline" element={P("app.view", <Pipeline />)} />
            <Route path="interviews" element={P("interview.view", <Interviews />)} />
            <Route path="offers" element={P("offer.view", <Offers />)} />
            <Route path="joining" element={P("joining.view", <Joining />)} />
            <Route path="costs" element={P("cost.view", <Costs />)} />
            <Route path="analytics" element={P("analytics.view", <Analytics />)} />
            <Route path="reports" element={P("reports.export", <Reports />)} />
            <Route path="import" element={P("import.run", <ImportPage />)} />
            <Route path="activity" element={P("activity.view", <Activity />)} />
            <Route path="users" element={P("users.manage", <UsersPage />)} />
            <Route path="settings" element={P("masters.manage", <SettingsPage />)} />
            <Route path="profile" element={<Profile />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster position="top-right" richColors />
    </AuthProvider>
  );
}
