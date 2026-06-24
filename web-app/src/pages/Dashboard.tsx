import { CreditCard, History, Send, Shield } from "lucide-react";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import {
  type AccountOut,
  type EnrollmentProgress,
  type ProfileOut,
  getProfile,
  getSessionToken,
  listAccounts,
} from "../api";
import AppHeader from "../components/AppHeader";
import CalibrationBanner from "../components/CalibrationBanner";
import TrustBadge from "../components/TrustBadge";

interface DashboardState {
  username?: string;
  trustScore?: number | null;
  behaviorMatch?: number | null;
  enrollment?: EnrollmentProgress | null;
}

function formatCurrency(amount: number | null, currency: string | null): string {
  if (amount === null) return "--";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: currency ?? "INR",
    maximumFractionDigits: 2,
  }).format(amount);
}

export default function Dashboard() {
  const navigate = useNavigate();
  const location = useLocation();
  const state = (location.state as DashboardState | null) ?? {};
  const username = state.username ?? "genuine";

  const [profile, setProfile] = useState<ProfileOut | null>(null);
  const [accounts, setAccounts] = useState<AccountOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getSessionToken();
    if (!token) {
      navigate("/login");
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const [profileRes, accountsRes] = await Promise.all([
          getProfile(token),
          listAccounts(token),
        ]);
        if (cancelled) return;
        if (profileRes.status === 200) setProfile(profileRes.body);
        if (accountsRes.status === 200) setAccounts(accountsRes.body);
      } catch {
        if (!cancelled) setError("Could not load account details.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  const displayName = profile?.full_name ?? username;

  return (
    <div className="min-h-screen bg-background-custom">
      <AppHeader username={displayName} />

      <main className="mx-auto max-w-5xl px-4 py-8 md:px-8">
        <div className="mb-8 flex flex-col gap-1">
          <h1 className="font-headline text-3xl font-bold text-on-surface">Welcome, {displayName}</h1>
          {profile?.kyc_level && (
            <span className="mt-1 inline-block w-max rounded bg-emerald-50 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-emerald-800">
              {profile.kyc_level}
            </span>
          )}
        </div>

        {loading && <p className="text-sm text-on-surface-variant">Loading accounts...</p>}
        {error && <p className="text-sm text-secondary">{error}</p>}
        {!loading && !error && accounts.length === 0 && (
          <p className="text-sm text-on-surface-variant">No accounts found.</p>
        )}

        {accounts.length > 0 && (
          <div className="mb-8 grid grid-cols-1 gap-6 md:grid-cols-2">
            {accounts.map((account) => (
              <div
                key={account.account_id}
                className="rounded-xl border border-t-4 border-outline-variant border-t-primary bg-surface-container-lowest p-6 shadow-sm transition-shadow hover:shadow-md"
              >
                <div className="mb-4 flex items-start justify-between">
                  <div>
                    <p className="text-[11px] font-bold uppercase tracking-wider text-on-surface-variant">
                      {account.account_type ?? "Account"}
                    </p>
                    <h2 className="font-headline text-lg font-bold text-on-surface">
                      {account.masked_account_number}
                    </h2>
                  </div>
                  <CreditCard className="h-6 w-6 text-primary" />
                </div>
                <p className="font-headline text-3xl font-bold text-primary">
                  {formatCurrency(account.balance, account.currency)}
                </p>
                <p className="mt-1 text-xs text-on-surface-variant">{account.status}</p>
              </div>
            ))}
          </div>
        )}

        <div className="mb-8">
          <h3 className="font-headline mb-4 text-lg font-bold text-on-surface">Quick Actions</h3>
          <div className="grid grid-cols-3 gap-3">
            <button
              type="button"
              onClick={() => navigate("/transfer", { state: { username: displayName } })}
              className="flex flex-col items-center justify-center rounded-xl border border-outline-variant bg-surface-container-lowest p-4 text-center transition-all hover:border-primary hover:bg-primary/5"
            >
              <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
                <Send className="h-4 w-4 text-primary" />
              </div>
              <span className="text-xs font-semibold text-on-surface">Transfer Funds</span>
            </button>
            <button
              type="button"
              onClick={() => navigate("/transactions", { state: { username: displayName } })}
              className="flex flex-col items-center justify-center rounded-xl border border-outline-variant bg-surface-container-lowest p-4 text-center transition-all hover:border-primary hover:bg-primary/5"
            >
              <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
                <History className="h-4 w-4 text-primary" />
              </div>
              <span className="text-xs font-semibold text-on-surface">Transaction History</span>
            </button>
            <button
              type="button"
              onClick={() => navigate("/security", { state: { username: displayName } })}
              className="flex flex-col items-center justify-center rounded-xl border border-outline-variant bg-surface-container-lowest p-4 text-center transition-all hover:border-primary hover:bg-primary/5"
            >
              <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
                <Shield className="h-4 w-4 text-primary" />
              </div>
              <span className="text-xs font-semibold text-on-surface">Security Settings</span>
            </button>
          </div>
        </div>

        <CalibrationBanner progress={state.enrollment} />
        <TrustBadge trustScore={state.trustScore} behaviorMatch={state.behaviorMatch} />
      </main>
    </div>
  );
}
