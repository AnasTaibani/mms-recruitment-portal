import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Bell, Briefcase, CalendarCheck, ChevronsLeft, FileCheck, FileSpreadsheet, History, IndianRupee, Kanban, LayoutDashboard, LogOut, Menu, PieChart, Settings, ShieldCheck, UserCircle, UserCheck, Users, Download } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { AssistantLauncher } from "@/components/assistant/AssistantDrawer";
import { useAuth } from "@/context/AuthContext";
import { api, fmtDateTime } from "@/lib/api";
import { cn } from "@/lib/utils";

export const NAV = [
  { group: "Overview", items: [{ to: "/", label: "Dashboard", icon: LayoutDashboard }] },
  { group: "Recruitment", items: [
    { to: "/requisitions", label: "Requisitions", icon: Briefcase, perm: "req.view" },
    { to: "/candidates", label: "Candidates", icon: Users, perm: "cand.view" },
    { to: "/pipeline", label: "Pipeline", icon: Kanban, perm: "app.view" },
    { to: "/interviews", label: "Interviews", icon: CalendarCheck, perm: "interview.view" },
    { to: "/offers", label: "Offers", icon: FileCheck, perm: "offer.view" },
    { to: "/joining", label: "Joining", icon: UserCheck, perm: "joining.view" },
    { to: "/costs", label: "Recruitment Costs", icon: IndianRupee, perm: "cost.view" },
  ] },
  { group: "Insights", items: [
    { to: "/analytics", label: "Analytics", icon: PieChart, perm: "analytics.view" },
    { to: "/reports", label: "Reports & Export", icon: Download, perm: "reports.export" },
  ] },
  { group: "Administration", items: [
    { to: "/import", label: "Data Import & Migration", icon: FileSpreadsheet, perm: "import.run" },
    { to: "/activity", label: "Activity Log", icon: History, perm: "activity.view" },
    { to: "/users", label: "Users & Roles", icon: ShieldCheck, perm: "users.manage" },
    { to: "/settings", label: "Master Data & Settings", icon: Settings, perm: "masters.manage" },
  ] },
];

function SideNav({ collapsed, onNavigate }) {
  const { can } = useAuth();
  return (
    <nav className="flex-1 space-y-6 overflow-y-auto px-3 py-5 scroll-thin">
      {NAV.map((g) => {
        const items = g.items.filter((i) => !i.perm || can(i.perm));
        if (!items.length) return null;
        return (
          <div key={g.group}>
            {!collapsed ? <p className="mb-1.5 px-3 text-[11px] font-medium uppercase tracking-[0.08em] text-[#8A929E]">{g.group}</p>
              : <div className="mx-auto mb-2 h-px w-6 bg-line" />}
            <div className="space-y-0.5">
              {items.map(({ to, label, icon: Icon }) => (
                <NavLink key={to} to={to} end={to === "/"} onClick={onNavigate} title={label} data-testid={`nav-${label.toLowerCase().replace(/[^a-z]+/g, "-")}`}
                  className={({ isActive }) => cn("group/nav relative flex h-10 items-center gap-3 rounded-[10px] px-3 text-[14px] font-medium transition-colors duration-150",
                    isActive ? "bg-brand-pale text-brand-deep" : "text-ink hover:bg-[#F3F6FA]", collapsed && "justify-center px-0")}>
                  {({ isActive }) => (<>
                    {isActive && <span className="absolute -left-3 top-2 h-6 w-[3px] rounded-r-full bg-brand-deep" />}
                    <Icon className={cn("h-[18px] w-[18px] shrink-0", isActive ? "text-brand-deep" : "text-subtle group-hover/nav:text-ink")} strokeWidth={1.8} />
                    {!collapsed && <span className="truncate">{label}</span>}
                  </>)}
                </NavLink>
              ))}
            </div>
          </div>
        );
      })}
    </nav>
  );
}

function Brand({ collapsed }) {
  return (
    <Link to="/" className="flex h-[76px] items-center border-b border-line px-5">
      {collapsed ? (
        <img src="/mms-mark.png" alt="MetaMorphoSys Technologies" className="mx-auto h-9 w-9 object-contain" />
      ) : (
        <div className="w-full leading-tight">
          <img src="/mms-logo.png" alt="MetaMorphoSys Technologies" className="h-10 w-auto max-w-[190px] object-contain" />
          <p className="mt-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-[#8A929E]">Recruitment Portal</p>
        </div>
      )}
    </Link>
  );
}

function Notifications() {
  const [data, setData] = useState({ items: [], unread: 0 });
  const nav = useNavigate();
  const load = () => api.get("/notifications").then((r) => setData(r.data)).catch(() => {});
  useEffect(() => { load(); const t = setInterval(load, 60000); return () => clearInterval(t); }, []);
  const open = async (n) => { await api.post(`/notifications/${n.id}/read`); load(); if (n.link) nav(n.link); };
  return (
    <Popover onOpenChange={(o) => o && load()}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" className="relative" data-testid="notifications-btn">
          <Bell className="h-[18px] w-[18px]" />
          {data.unread > 0 && <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-brand-deep px-1 text-[10px] font-semibold text-white ring-2 ring-white" data-testid="notifications-count">{data.unread > 99 ? "99+" : data.unread}</span>}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[360px] p-0">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <p className="text-sm font-semibold">Notifications</p>
          <button className="text-xs text-subtle hover:text-ink" onClick={async () => { await api.post("/notifications/read-all"); load(); }} data-testid="notifications-read-all">Mark all read</button>
        </div>
        <div className="max-h-96 overflow-y-auto">
          {!data.items.length && <p className="p-6 text-center text-sm text-[#9AA2AE]">You're all caught up.</p>}
          {data.items.map((n) => (
            <button key={n.id} onClick={() => open(n)} className={cn("block w-full border-b border-[#EEF1F5] px-4 py-3 text-left hover:bg-canvas", !n.read && "bg-brand-mist")} data-testid="notification-item">
              <p className="text-sm font-medium text-ink">{!n.read && <span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-brand-deep align-middle" />}{n.title}</p>
              <p className="text-xs text-[#4B5361]">{n.message}</p>
              <p className="mt-0.5 text-[10px] text-[#9AA2AE]">{fmtDateTime(n.created_at)}</p>
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}

function crumbs(path) {
  const all = NAV.flatMap((g) => g.items.map((i) => ({ ...i, group: g.group })));
  const seg = "/" + (path.split("/")[1] || "");
  const item = all.find((i) => i.to === seg) || (seg === "/profile" ? { label: "My Profile", group: "Account", to: "/profile" } : all[0]);
  const parts = [{ label: item.group }, { label: item.label, to: item.to }];
  if (path.split("/")[2]) parts.push({ label: "Details" });
  return parts;
}

export default function AppShell() {
  const { user, logout } = useAuth();
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("mms-sidebar") === "1");
  const [mobile, setMobile] = useState(false);
  const loc = useLocation();
  const nav = useNavigate();
  const parts = crumbs(loc.pathname);
  useEffect(() => { localStorage.setItem("mms-sidebar", collapsed ? "1" : "0"); }, [collapsed]);
  const initials = user.name.split(" ").map((x) => x[0]).slice(0, 2).join("").toUpperCase();

  return (
    <div className="flex min-h-screen bg-canvas">
      <aside className={cn("sticky top-0 hidden h-screen shrink-0 flex-col border-r border-line bg-white transition-[width] duration-200 lg:flex", collapsed ? "w-[76px]" : "w-[248px]")} data-testid="sidebar">
        <Brand collapsed={collapsed} />
        <SideNav collapsed={collapsed} />
        <button onClick={() => setCollapsed(!collapsed)} className={cn("flex h-12 items-center gap-2 border-t border-line px-6 text-[13px] text-subtle transition-colors hover:text-brand-deep", collapsed && "justify-center px-0")} data-testid="sidebar-toggle">
          <ChevronsLeft className={cn("h-4 w-4 transition-transform", collapsed && "rotate-180")} />{!collapsed && "Collapse"}
        </button>
      </aside>
      <Sheet open={mobile} onOpenChange={setMobile}>
        <SheetContent side="left" className="flex w-72 flex-col p-0"><Brand /><SideNav onNavigate={() => setMobile(false)} /></SheetContent>
      </Sheet>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-line bg-white/90 px-4 backdrop-blur-md sm:px-6 lg:px-8">
          <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobile(true)} data-testid="mobile-menu-btn"><Menu className="h-5 w-5" /></Button>
          <div className="min-w-0">
            <p className="truncate text-[15px] font-semibold text-ink sm:hidden" data-testid="topbar-title">{parts[1].label}</p>
            <div className="hidden items-center gap-1.5 text-[12px] text-subtle sm:flex" data-testid="breadcrumbs">
              <span>MMS</span>{parts.map((p, i) => <span key={i} className="flex items-center gap-1.5"><span className="text-[#C6CDD6]">/</span>{p.to && i < parts.length - 1 ? <Link to={p.to} className="hover:text-brand-deep">{p.label}</Link> : <span className={cn(i === parts.length - 1 && "font-medium text-ink")}>{p.label}</span>}</span>)}
            </div>
          </div>
          <div className="ml-auto flex items-center gap-1">
            <Notifications />
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="flex items-center gap-2.5 rounded-[10px] py-1 pl-1 pr-2 transition-colors hover:bg-[#F3F6FA]" data-testid="user-menu-btn">
                  <span className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-deep text-[12px] font-semibold text-white">{initials}</span>
                  <span className="hidden text-left leading-tight sm:block"><span className="block text-[13px] font-semibold text-ink">{user.name}</span><span className="block text-[12px] text-subtle">{user.designation || user.role_label}</span></span>
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-52">
                <DropdownMenuLabel className="text-xs font-normal text-subtle">{user.email}</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => nav("/profile")} data-testid="menu-profile"><UserCircle className="mr-2 h-4 w-4" />My profile</DropdownMenuItem>
                <DropdownMenuItem onClick={async () => { await logout(); nav("/login"); }} data-testid="menu-logout"><LogOut className="mr-2 h-4 w-4" />Sign out</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1440px] flex-1 px-4 pb-24 pt-6 sm:px-6 lg:px-8 lg:pt-7"><Outlet /></main>
        {/* keyed by user: a different sign-in starts with an empty assistant; signing out unmounts it */}
        <AssistantLauncher key={user.id} />
      </div>
    </div>
  );
}
