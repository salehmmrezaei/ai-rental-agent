import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  Heart,
  FileText,
  KeyRound,
  CalendarDays,
  MessageSquare,
  UserRound,
  Building2,
  ChartNoAxesCombined,
  UsersRound,
  ClipboardCheck,
  LogOut,
  ArrowUpRight,
  Menu,
  X,
  Sparkles,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useAuth } from "../auth/AuthProvider";
import { Brand } from "./PublicLayout";
import { Button, Feedback } from "../components/ui";
import { useAction } from "../hooks/useAction";
import type { Role } from "../api/types";
type NavItem = [string, string, LucideIcon];
const menus: Record<Role, NavItem[]> = {
  tenant: [
    ["", "Overview", LayoutDashboard],
    ["assistant", "AI assistant", Sparkles],
    ["saved", "Saved homes", Heart],
    ["applications", "Applications", FileText],
    ["contracts", "My rentals", KeyRound],
    ["visits", "Property visits", CalendarDays],
    ["messages", "Agency messages", MessageSquare],
    ["profile", "My profile", UserRound],
  ],
  landlord: [
    ["", "Overview", LayoutDashboard],
    ["properties", "My properties", Building2],
    ["occupancy", "Occupancy", ChartNoAxesCombined],
    ["contracts", "Rental history", KeyRound],
    ["profile", "My profile", UserRound],
  ],
  admin: [
    ["", "Overview", LayoutDashboard],
    ["users", "Users", UsersRound],
    ["properties", "Properties", Building2],
    ["listings", "Listing approvals", ClipboardCheck],
    ["applications", "Applications", FileText],
    ["contracts", "Contracts", KeyRound],
    ["visits", "Visit scheduling", CalendarDays],
    ["messages", "Messaging inbox", MessageSquare],
    ["occupancy", "Occupancy reports", ChartNoAxesCombined],
    ["profile", "My profile", UserRound],
  ],
};
export function DashboardLayout() {
  const auth = useAuth();
  const location = useLocation();
  const action = useAction();
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [open]);
  const user = auth.user!;
  const label =
    menus[user.role].find(
      ([path]) => path && location.pathname.includes(`/${path}`),
    )?.[1] || "Overview";
  return (
    <div className="dashboard-layout">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="sidebar-brand">
          <Brand />
          <button
            className="icon-button mobile-menu"
            onClick={() => setOpen(false)}
            aria-label="Close navigation"
          >
            <X size={20} />
          </button>
        </div>
        <p className="sidebar-caption">
          {user.role === "admin"
            ? "Agency workspace"
            : `${user.role} workspace`}
        </p>
        <nav id="dashboard-navigation" aria-label="Dashboard navigation">
          {menus[user.role].map(([path, title, Icon]) => (
            <NavLink
              key={path}
              end={!path}
              to={`/${user.role}${path ? `/${path}` : ""}`}
              onClick={() => setOpen(false)}
            >
              <Icon size={19} />
              {title}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <Link to="/listings" className="sidebar-explore">
            Explore homes
            <ArrowUpRight size={17} />
          </Link>
          <div className="user-chip">
            <span className="avatar">
              {user.full_name.slice(0, 1).toUpperCase()}
            </span>
            <div>
              <strong>{user.full_name}</strong>
              <small>
                {user.role === "admin" ? "Rental agency" : user.role}
              </small>
            </div>
          </div>
          <Button
            variant="ghost"
            pending={action.pending}
            onClick={() => void action.run(auth.signOut)}
          >
            <LogOut size={17} />
            Sign out
          </Button>
        </div>
      </aside>
      {open && (
        <button
          className="sidebar-backdrop"
          aria-label="Close navigation"
          onClick={() => setOpen(false)}
        />
      )}
      <div className="dashboard-main">
        <header className="dashboard-topbar">
          <div className="flex items-center gap-3">
            <button
              className="icon-button mobile-menu"
              aria-label="Open navigation"
              aria-expanded={open}
              aria-controls="dashboard-navigation"
              onClick={() => setOpen(true)}
            >
              <Menu size={21} />
            </button>
            <span className="breadcrumb">
              Workspace <span>/</span> <strong>{label}</strong>
            </span>
          </div>
          <Link to="/listings" className="text-link">
            Find a home
            <ArrowUpRight size={15} />
          </Link>
        </header>
        <main id="main" className="dashboard-content">
          <Feedback error={action.error} />
          <Outlet />
        </main>
        <footer className="dashboard-footer">
          Casa · Rental management <span>All times in Europe/Rome</span>
        </footer>
      </div>
    </div>
  );
}
