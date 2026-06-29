import { Activity, BookOpen, FileText, LogOut, Shield } from "lucide-react";
import { NavLink, useNavigate } from "react-router-dom";

import { clearAdminToken } from "../api";

const LINKS = [
  { to: "/", label: "Live Feed", icon: Activity },
  { to: "/cases", label: "Cases", icon: FileText },
  { to: "/policy", label: "Policy", icon: BookOpen },
  { to: "/governance", label: "Governance", icon: Shield },
];

export default function NavBar() {
  const navigate = useNavigate();

  function handleLogout() {
    clearAdminToken();
    navigate("/login");
  }

  return (
    <aside className="fixed inset-y-0 left-0 z-20 flex w-56 flex-col border-r border-soc-border bg-soc-surface shadow-sm">
      {/* Brand */}
      <div className="flex items-center gap-3 px-5 py-5 border-b border-soc-border">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-soc-primary text-xs font-bold text-white">
          CG
        </span>
        <div className="flex flex-col leading-tight">
          <span className="font-headline text-sm font-bold text-soc-primary">CogniGuard SOC</span>
          <span className="text-[9px] font-semibold uppercase tracking-widest text-soc-muted">Fraud Operations</span>
        </div>
      </div>

      {/* Nav links */}
      <nav className="flex-1 space-y-1 px-3 py-4">
        {LINKS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-soc-primary-light text-soc-primary"
                  : "text-soc-muted hover:bg-soc-bg hover:text-soc-text"
              }`
            }
          >
            <Icon className="h-4 w-4 shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Sign Out pinned at bottom */}
      <div className="border-t border-soc-border px-3 py-4">
        <button
          onClick={handleLogout}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-soc-muted transition-colors hover:bg-soc-danger-light hover:text-soc-danger"
        >
          <LogOut className="h-4 w-4 shrink-0" />
          Sign Out
        </button>
      </div>
    </aside>
  );
}
