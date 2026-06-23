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
    <div className="mx-auto mt-16 max-w-md rounded border p-6 shadow-sm">
      <h1 className="text-xl font-semibold">Welcome, {displayName}</h1>

      {loading && <p className="mt-2 text-sm text-gray-500">Loading accounts...</p>}
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

      {!loading && !error && accounts.length === 0 && (
        <p className="mt-2 text-sm text-gray-500">No accounts found.</p>
      )}

      {accounts.map((account) => (
        <div key={account.account_id} className="mt-3 border-t pt-3 first:mt-2 first:border-t-0 first:pt-0">
          <p className="text-3xl font-bold">{formatCurrency(account.balance, account.currency)}</p>
          <p className="text-sm text-gray-500">
            {account.account_type ?? "Account"} &middot; {account.masked_account_number}
          </p>
        </div>
      ))}

      <CalibrationBanner progress={state.enrollment} />
      <TrustBadge trustScore={state.trustScore} behaviorMatch={state.behaviorMatch} />

      <button
        type="button"
        className="mt-6 w-full rounded bg-blue-600 px-3 py-2 text-white"
        onClick={() => navigate("/transfer", { state: { username: displayName } })}
      >
        Transfer funds
      </button>
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          className="w-full rounded border px-3 py-2 text-sm text-gray-700"
          onClick={() => navigate("/transactions", { state: { username: displayName } })}
        >
          Transaction history
        </button>
        <button
          type="button"
          className="w-full rounded border px-3 py-2 text-sm text-gray-700"
          onClick={() => navigate("/security", { state: { username: displayName } })}
        >
          Security settings
        </button>
      </div>
    </div>
  );
}
