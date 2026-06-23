import { useNavigate } from "react-router-dom";

interface AppHeaderProps {
  username?: string;
}

// Shared top bar for authenticated pages (Dashboard/Transfer/Transactions/Security).
export default function AppHeader({ username }: AppHeaderProps) {
  const navigate = useNavigate();

  return (
    <header className="bg-cbi-primary text-white shadow-sm">
      <div className="mx-auto flex max-w-md items-center justify-between px-4 py-3">
        <button
          type="button"
          className="flex items-center gap-2"
          onClick={() => navigate("/dashboard", { state: { username } })}
        >
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-white text-sm font-bold text-cbi-primary">
            CB
          </span>
          <span className="text-base font-semibold tracking-tight">CogniGuard Bank</span>
        </button>
        {username && <span className="text-sm text-cbi-primary-light">{username}</span>}
      </div>
    </header>
  );
}
