import { LogOut } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { clearSessionToken } from "../api";

interface AppHeaderProps {
  username?: string;
}

// Shared top bar for authenticated pages (Dashboard/Transfer/Transactions/Security).
export default function AppHeader({ username }: AppHeaderProps) {
  const navigate = useNavigate();

  function handleLogout() {
    clearSessionToken();
    navigate("/login");
  }

  return (
    <header className="bg-primary text-on-primary shadow-md">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3 md:px-8">
        <button
          type="button"
          className="flex items-center gap-2"
          onClick={() => navigate("/dashboard", { state: { username } })}
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-full bg-white text-sm font-bold text-primary">
            HT
          </span>
          <span className="font-headline text-base font-bold tracking-tight md:text-lg">Heritage Trust Bank</span>
        </button>
        <div className="flex items-center gap-4">
          {username && <span className="hidden text-sm text-on-primary-container md:block">{username}</span>}
          <button
            type="button"
            onClick={handleLogout}
            className="flex items-center gap-1.5 rounded bg-secondary px-3 py-1.5 text-xs font-semibold text-on-secondary transition-all hover:opacity-90 active:scale-95"
          >
            <LogOut className="h-3.5 w-3.5" />
            <span>Logout</span>
          </button>
        </div>
      </div>
    </header>
  );
}
