import { ArrowUpRight, CreditCard, History, Search, Send, Shield, ShieldAlert, User } from "lucide-react";
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
import { useSessionIngest } from "../hooks/useSessionIngest";

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

function formatDate(iso: string | null): string {
  if (!iso) return "--";
  try {
    return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(iso));
  } catch {
    return iso;
  }
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

  const { reauthRequired, sessionTerminated, dismissReauth } = useSessionIngest();

  useEffect(() => {
    if (sessionTerminated) navigate("/login");
  }, [sessionTerminated, navigate]);

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
  const firstName = displayName.split(" ")[0];
  const initials = displayName
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);
  const primaryAccount = accounts[0] ?? null;

  const filteredTransactions = transactions.filter(
    (tx) =>
      (tx.beneficiary_name ?? "").toLowerCase().includes(searchQuery.toLowerCase()) ||
      (tx.transfer_type ?? "").toLowerCase().includes(searchQuery.toLowerCase()),
  );

  return (
    <div className="flex min-h-screen flex-col bg-background-custom">
      <AppHeader username={displayName} />

      {/* Security re-auth alert */}
      {reauthRequired && (
        <div className="border-b border-orange-200 bg-orange-50 px-4 py-3">
          <div className="mx-auto flex max-w-6xl items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <ShieldAlert className="h-5 w-5 shrink-0 text-orange-500" />
              <p className="text-sm font-semibold text-orange-800">
                Unusual activity detected. Please verify your identity to continue.
              </p>
            </div>
            <button
              type="button"
              onClick={dismissReauth}
              className="shrink-0 rounded-lg bg-orange-500 px-4 py-1.5 text-xs font-bold text-white hover:bg-orange-600"
            >
              Acknowledged
            </button>
          </div>
        </div>
      )}

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 md:px-8">

        {/* Hero: Greeting + Primary Account Card */}
        <div className="mb-6 grid gap-4 md:grid-cols-3">

          {/* Greeting card */}
          <div className="flex flex-col justify-between rounded-2xl bg-primary p-6 text-white md:col-span-2">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-primary-fixed/80">Good day,</p>
                <h1 className="font-headline text-2xl font-bold md:text-3xl">{firstName}</h1>
                {profile?.kyc_level && (
                  <span className="mt-1 inline-block rounded-full bg-white/15 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">
                    {profile.kyc_level} Verified
                  </span>
                )}
              </div>
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-white/20 text-lg font-bold">
                {initials}
              </div>
            </div>

            {primaryAccount && (
              <div className="rounded-xl bg-white/10 p-4">
                <p className="text-xs font-medium uppercase tracking-widest text-primary-fixed/70">
                  {primaryAccount.account_type ?? "Savings"} Account
                </p>
                <p className="mt-1 font-mono text-sm text-primary-fixed/80">{primaryAccount.masked_account_number}</p>
                <p className="font-headline mt-2 text-3xl font-bold text-white">
                  {formatCurrency(primaryAccount.balance, primaryAccount.currency)}
                </p>
                <p className="mt-1 text-xs capitalize text-primary-fixed/70">{primaryAccount.status}</p>
              </div>
            )}

            {loading && <p className="text-sm text-white/70">Loading accounts…</p>}
            {!loading && !error && accounts.length === 0 && (
              <p className="text-sm text-white/70">No accounts found.</p>
            )}
            {error && <p className="text-sm text-red-300">{error}</p>}
          </div>

          {/* Quick actions */}
          <div className="flex flex-col gap-3">
            <h3 className="font-headline text-sm font-bold uppercase tracking-wider text-on-surface-variant">Quick Actions</h3>
            {[
              { icon: Send, label: "Transfer", sub: "NEFT / IMPS / UPI", path: "/transfer", accent: true },
              { icon: History, label: "History", sub: "View all transactions", path: "/transactions", accent: false },
              { icon: Shield, label: "Security", sub: "Devices & sessions", path: "/security", accent: false },
              { icon: User, label: "Profile", sub: "Account settings", path: "/profile", accent: false },
            ].map(({ icon: Icon, label, sub, path, accent }) => (
              <button
                key={path}
                type="button"
                onClick={() => navigate(path, { state: { username: displayName } })}
                className={`group flex items-center gap-3 rounded-xl border p-3.5 text-left transition-all hover:shadow-sm active:scale-[0.98] ${
                  accent
                    ? "border-primary bg-primary/5 hover:bg-primary hover:text-white"
                    : "border-outline-variant bg-white hover:border-primary/40 hover:bg-primary/5"
                }`}
              >
                <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${accent ? "bg-primary group-hover:bg-white/20" : "bg-primary/10"}`}>
                  <Icon className={`h-4 w-4 ${accent ? "text-white group-hover:text-white" : "text-primary"}`} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className={`text-sm font-semibold ${accent ? "text-primary group-hover:text-white" : "text-on-surface"}`}>{label}</p>
                  <p className={`text-[11px] ${accent ? "text-primary/70 group-hover:text-white/70" : "text-on-surface-variant"}`}>{sub}</p>
                </div>
                <ArrowUpRight className={`h-4 w-4 shrink-0 opacity-0 transition-opacity group-hover:opacity-100 ${accent ? "text-white" : "text-primary"}`} />
              </button>
            ))}
          </div>
        </div>

        {/* Calibration & Trust */}
        <div className="mb-6 space-y-3">
          <CalibrationBanner progress={state.enrollment} />
          <TrustBadge trustScore={state.trustScore} behaviorMatch={state.behaviorMatch} />
        </div>

        {/* All accounts (if more than one) */}
        {accounts.length > 1 && (
          <div className="mb-6">
            <h3 className="font-headline mb-3 text-lg font-bold text-on-surface">All Accounts</h3>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {accounts.slice(1).map((account) => (
                <div
                  key={account.account_id}
                  className="rounded-xl border border-outline-variant bg-white p-5 shadow-sm"
                >
                  <div className="mb-3 flex items-center justify-between">
                    <p className="text-[11px] font-bold uppercase tracking-wider text-on-surface-variant">
                      {account.account_type ?? "Account"}
                    </p>
                    <CreditCard className="h-5 w-5 text-primary/60" />
                  </div>
                  <p className="font-mono text-xs text-on-surface-variant">{account.masked_account_number}</p>
                  <p className="font-headline mt-2 text-2xl font-bold text-on-surface">
                    {formatCurrency(account.balance, account.currency)}
                  </p>
                  <p className="mt-1 text-[10px] capitalize text-on-surface-variant">{account.status}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recent Transactions */}
        <div className="rounded-2xl border border-outline-variant bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-outline-variant px-6 py-4">
            <h3 className="font-headline text-lg font-bold text-on-surface">Recent Transactions</h3>
            <div className="flex items-center gap-3">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search…"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-40 rounded-full border border-outline-variant bg-background-custom py-1.5 pl-8 pr-3 text-xs outline-none focus:border-primary focus:w-52 transition-all"
                />
              </div>
              <div className="flex gap-1.5">
                {[5, 10].map((n) => (
                  <button
                    key={n}
                    type="button"
                    onClick={() => setTransactionLimit(n)}
                    className={`rounded-full px-3 py-1 text-xs font-semibold transition-colors ${
                      transactionLimit === n ? "bg-primary text-white" : "bg-surface-container-low text-on-surface-variant hover:bg-primary/10"
                    }`}
                  >
                    {n}
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={() => navigate("/transactions", { state: { username: displayName } })}
                className="hidden text-xs font-semibold text-primary hover:underline md:block"
              >
                View all →
              </button>
            </div>
          </div>

          <div className="divide-y divide-outline-variant">
            {loading && (
              <p className="px-6 py-8 text-center text-sm text-on-surface-variant">Loading transactions…</p>
            )}
            {!loading && filteredTransactions.length === 0 && (
              <p className="px-6 py-8 text-center text-sm text-on-surface-variant">No transactions found.</p>
            )}
            {filteredTransactions.map((tx) => {
              const isDebit = (tx.amount ?? 0) < 0;
              return (
                <div key={tx.transaction_id} className="flex items-center gap-4 px-6 py-4 transition-colors hover:bg-surface-container-low">
                  <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${isDebit ? "bg-secondary/10" : "bg-success-custom/10"}`}>
                    <Send className={`h-4 w-4 ${isDebit ? "text-secondary" : "text-success-custom rotate-180"}`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="truncate text-sm font-semibold text-on-surface">
                      {tx.beneficiary_name ?? tx.masked_beneficiary_account ?? "Transfer"}
                    </p>
                    <p className="mt-0.5 text-[11px] text-on-surface-variant">
                      {tx.transfer_type} · {tx.status} · {formatDate(tx.initiated_at)}
                    </p>
                  </div>
                  <p className={`shrink-0 text-sm font-bold ${isDebit ? "text-secondary" : "text-success-custom"}`}>
                    {isDebit ? "-" : "+"}{formatCurrency(Math.abs(tx.amount ?? 0), tx.currency)}
                  </p>
                </div>
              );
            })}
          </div>

          {!loading && filteredTransactions.length > 0 && (
            <div className="border-t border-outline-variant px-6 py-3 text-center">
              <button
                type="button"
                onClick={() => navigate("/transactions", { state: { username: displayName } })}
                className="text-xs font-semibold text-primary hover:underline"
              >
                View all transactions →
              </button>
            </div>
          )}
        </div>
      </main>

      <Footer />
    </div>
  );
}
