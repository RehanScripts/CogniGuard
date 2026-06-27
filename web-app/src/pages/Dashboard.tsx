import { CreditCard, History, RefreshCw, Search, Send, Shield } from "lucide-react";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import {
  type AccountOut,
  type EnrollmentProgress,
  type ProfileOut,
  type TransactionOut,
  getProfile,
  getSessionToken,
  listAccounts,
  listTransactions,
} from "../api";
import AppHeader from "../components/AppHeader";
import CalibrationBanner from "../components/CalibrationBanner";
import Footer from "../components/Footer";
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
  const [transactions, setTransactions] = useState<TransactionOut[]>([]);
  const [transactionLimit, setTransactionLimit] = useState(5);
  const [searchQuery, setSearchQuery] = useState("");
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
        const [profileRes, accountsRes, transactionsRes] = await Promise.all([
          getProfile(token),
          listAccounts(token),
          listTransactions(token, transactionLimit),
        ]);
        if (cancelled) return;
        if (profileRes.status === 200) setProfile(profileRes.body);
        if (accountsRes.status === 200) setAccounts(accountsRes.body);
        if (transactionsRes.status === 200) setTransactions(transactionsRes.body);
      } catch {
        if (!cancelled) setError("Could not load account details.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [navigate, transactionLimit]);

  const displayName = profile?.full_name ?? username;
  const filteredTransactions = transactions.filter(
    (tx) =>
      (tx.beneficiary_name ?? "").toLowerCase().includes(searchQuery.toLowerCase()) ||
      (tx.transfer_type ?? "").toLowerCase().includes(searchQuery.toLowerCase()),
  );

  return (
    <div className="flex min-h-screen flex-col bg-background-custom">
      <AppHeader username={displayName} />

      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 md:px-8">
        <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div className="flex flex-col gap-1">
            <h1 className="font-headline text-3xl font-bold text-on-surface">Welcome, {displayName}</h1>
            {profile?.kyc_level && (
              <span className="mt-1 inline-block w-max rounded bg-emerald-50 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-emerald-800">
                {profile.kyc_level}
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={() => navigate("/transfer", { state: { username: displayName } })}
            className="flex shrink-0 items-center gap-2 rounded-lg bg-primary px-6 py-3 text-sm font-bold text-on-primary shadow-md transition-all hover:opacity-90 active:scale-95"
          >
            <RefreshCw className="h-4 w-4" />
            <span>Quick Transfer</span>
          </button>
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

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-1">
            <div>
              <h3 className="font-headline mb-4 text-lg font-bold text-on-surface">Quick Actions</h3>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => navigate("/transfer", { state: { username: displayName } })}
                  className="group flex flex-col items-center justify-center rounded-xl border border-outline-variant bg-surface-container-lowest p-4 text-center transition-all hover:border-primary hover:bg-primary/5"
                >
                  <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 transition-all group-hover:bg-primary">
                    <Send className="h-4 w-4 text-primary group-hover:text-white" />
                  </div>
                  <span className="text-xs font-semibold text-on-surface">Transfer Funds</span>
                </button>
                <button
                  type="button"
                  onClick={() => navigate("/transactions", { state: { username: displayName } })}
                  className="group flex flex-col items-center justify-center rounded-xl border border-outline-variant bg-surface-container-lowest p-4 text-center transition-all hover:border-primary hover:bg-primary/5"
                >
                  <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 transition-all group-hover:bg-primary">
                    <History className="h-4 w-4 text-primary group-hover:text-white" />
                  </div>
                  <span className="text-xs font-semibold text-on-surface">Transaction History</span>
                </button>
                <button
                  type="button"
                  onClick={() => navigate("/security", { state: { username: displayName } })}
                  className="group col-span-2 flex flex-col items-center justify-center rounded-xl border border-outline-variant bg-surface-container-lowest p-4 text-center transition-all hover:border-primary hover:bg-primary/5"
                >
                  <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 transition-all group-hover:bg-primary">
                    <Shield className="h-4 w-4 text-primary group-hover:text-white" />
                  </div>
                  <span className="text-xs font-semibold text-on-surface">Security Settings</span>
                </button>
              </div>
            </div>

            <CalibrationBanner progress={state.enrollment} />
            <TrustBadge trustScore={state.trustScore} behaviorMatch={state.behaviorMatch} />
          </div>

          <div className="space-y-4 lg:col-span-2">
            <div className="flex items-center justify-between">
              <h3 className="font-headline text-lg font-bold text-on-surface">Recent Transactions</h3>
              <div className="flex gap-2 text-xs">
                <button
                  type="button"
                  onClick={() => setTransactionLimit(5)}
                  className={`rounded px-2.5 py-1 font-semibold ${transactionLimit === 5 ? "bg-primary text-white" : "bg-slate-100 text-slate-600"}`}
                >
                  5 records
                </button>
                <button
                  type="button"
                  onClick={() => setTransactionLimit(10)}
                  className={`rounded px-2.5 py-1 font-semibold ${transactionLimit === 10 ? "bg-primary text-white" : "bg-slate-100 text-slate-600"}`}
                >
                  10 records
                </button>
              </div>
            </div>

            <div className="overflow-hidden rounded-xl border border-outline-variant bg-surface-container-lowest shadow-sm">
              <div className="border-b border-outline-variant bg-slate-50/50 px-5 py-4">
                <div className="relative w-full max-w-xs">
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <input
                    type="text"
                    placeholder="Search transactions..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full rounded-full border border-outline-variant bg-white py-2 pl-9 pr-4 text-xs outline-none focus:border-primary"
                  />
                </div>
              </div>

              <div className="divide-y divide-outline-variant">
                {filteredTransactions.length === 0 ? (
                  <p className="px-5 py-8 text-center text-xs text-slate-400">No matching transactions found.</p>
                ) : (
                  filteredTransactions.map((tx) => (
                    <div key={tx.transaction_id} className="flex items-center justify-between px-5 py-4 transition-colors hover:bg-slate-50">
                      <div>
                        <p className="text-sm font-bold text-on-surface">
                          {tx.beneficiary_name ?? tx.masked_beneficiary_account ?? "--"}
                        </p>
                        <p className="mt-0.5 text-[10px] text-on-surface-variant">
                          {tx.transfer_type} &middot; {tx.status} &middot; {tx.initiated_at ?? "--"}
                        </p>
                      </div>
                      <p className="text-sm font-bold text-secondary">{formatCurrency(tx.amount, tx.currency)}</p>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      </main>
      <Footer />
    </div>
  );
}
