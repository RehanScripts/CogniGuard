import { History, LayoutDashboard, LogOut, Send, Shield, User } from "lucide-react";
import { NavLink, useNavigate } from "react-router-dom";

import logo from "../assets/logo.jpeg";
import { clearSessionToken } from "../api";

interface AppHeaderProps {
  username?: string;
}

export default function AppHeader({ username }: AppHeaderProps) {
  const navigate = useNavigate();

  function handleLogout() {
    clearSessionToken();
    navigate("/login");
  }

  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
      isActive
        ? "bg-primary/10 text-primary"
        : "text-on-surface-variant hover:text-primary hover:bg-primary/5"
    }`;

  return (
    <header className="sticky top-0 z-20 border-b border-outline-variant bg-white shadow-sm">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 md:px-8">
        {/* Brand */}
        <button
          type="button"
          className="flex shrink-0 items-center gap-2"
          onClick={() => navigate("/dashboard", { state: { username } })}
        >
          <span className="flex h-9 w-9 items-center justify-center overflow-hidden rounded-full bg-primary p-1">
            <img src={logo} alt="Heritage Trust Bank" className="h-full w-full object-contain" />
          </span>
          <div className="flex flex-col text-left leading-tight">
            <span className="font-headline text-sm font-bold text-primary md:text-base">Heritage Trust Bank</span>
            <span className="hidden text-[10px] tracking-widest text-on-surface-variant md:block">INTERNET BANKING</span>
          </div>
        </button>

        {/* Navigation links (hidden on small screens) */}
        <nav className="hidden items-center gap-1 md:flex">
          <NavLink to="/dashboard" state={{ username }} className={navLinkClass}>
            <LayoutDashboard className="h-4 w-4" />
            <span>Dashboard</span>
          </NavLink>
          <NavLink to="/transfer" state={{ username }} className={navLinkClass}>
            <Send className="h-4 w-4" />
            <span>Transfer</span>
          </NavLink>
          <NavLink to="/transactions" state={{ username }} className={navLinkClass}>
            <History className="h-4 w-4" />
            <span>History</span>
          </NavLink>
          <NavLink to="/security" state={{ username }} className={navLinkClass}>
            <Shield className="h-4 w-4" />
            <span>Security</span>
          </NavLink>
        </nav>

        {/* Right side: username + logout */}
        <div className="flex items-center gap-3">
          {username && (
            <button
              type="button"
              onClick={() => navigate("/profile", { state: { username } })}
              className="hidden items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-on-surface-variant transition-colors hover:bg-surface-container-low hover:text-primary md:flex"
            >
              <User className="h-4 w-4" />
              <span>{username}</span>
            </button>
          )}
          <button
            type="button"
            onClick={handleLogout}
            className="flex items-center gap-1.5 rounded-lg border border-outline-variant px-3 py-1.5 text-xs font-semibold text-on-surface-variant transition-all hover:border-secondary hover:text-secondary active:scale-95"
          >
            <LogOut className="h-3.5 w-3.5" />
            <span className="hidden md:block">Sign Out</span>
          </button>
        </div>
      </div>
    </header>
  );
}
