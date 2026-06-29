import { Building2, CreditCard, Mail, Shield, User } from "lucide-react";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { type AccountOut, type ProfileOut, getProfile, getSessionToken, listAccounts } from "../api";
import AppHeader from "../components/AppHeader";
import Footer from "../components/Footer";

function formatCurrency(amount: number | null, currency: string | null): string {
  if (amount === null) return "--";
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: currency ?? "INR", maximumFractionDigits: 2 }).format(amount);
}

export default function Profile() {
  const navigate = useNavigate();
  const location = useLocation();
  const state = (location.state as { username?: string } | null) ?? {};

  const [profile, setProfile] = useState<ProfileOut | null>(null);
  const [accounts, setAccounts] = useState<AccountOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getSessionToken();
    if (!token) { navigate("/login"); return; }
    let cancelled = false;
    (async () => {
      try {
        const [profileRes, accountsRes] = await Promise.all([getProfile(token), listAccounts(token)]);
        if (cancelled) return;
        if (profileRes.status === 200) setProfile(profileRes.body);
        if (accountsRes.status === 200) setAccounts(accountsRes.body);
      } catch {
        if (!cancelled) setError("Could not load profile.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [navigate]);

  const displayName = profile?.full_name ?? state.username ?? "User";
  const initials = displayName
    .split(" ")
    .map((n: string) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  return (
    <div className="flex min-h-screen flex-col bg-background-custom">
      <AppHeader username={displayName} />

      <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-8 md:px-8">
        <div className="mb-6">
          <h1 className="font-headline text-2xl font-bold text-on-surface">My Profile</h1>
          <p className="mt-1 text-sm text-on-surface-variant">Manage your account information</p>
        </div>

        {loading && <p className="text-sm text-on-surface-variant">Loading profile…</p>}
        {error && <p className="text-sm text-secondary">{error}</p>}

        {!loading && !error && (
          <div className="grid gap-6 md:grid-cols-3">
            {/* Avatar + name */}
            <div className="flex flex-col items-center gap-4 rounded-2xl border border-outline-variant bg-white p-8 shadow-sm md:col-span-1">
              <div className="flex h-20 w-20 items-center justify-center rounded-full bg-primary text-3xl font-bold text-white">
                {initials}
              </div>
              <div className="text-center">
                <p className="font-headline text-xl font-bold text-on-surface">{displayName}</p>
                {profile?.kyc_level && (
                  <span className="mt-1 inline-block rounded-full bg-emerald-50 px-3 py-0.5 text-xs font-bold uppercase tracking-wider text-emerald-700">
                    {profile.kyc_level}
                  </span>
                )}
              </div>
              <div className="mt-2 w-full rounded-xl bg-surface-container-low p-3 text-center">
                <p className="text-xs text-on-surface-variant">Account Status</p>
                <p className={`mt-0.5 text-sm font-bold capitalize ${profile?.account_status === "active" ? "text-success-custom" : "text-secondary"}`}>
                  {profile?.account_status ?? "--"}
                </p>
              </div>
            </div>

            {/* Details */}
            <div className="space-y-4 md:col-span-2">
              <div className="rounded-2xl border border-outline-variant bg-white p-6 shadow-sm">
                <h2 className="font-headline mb-4 text-base font-bold text-on-surface">Personal Information</h2>
                <div className="space-y-4">
                  {[
                    { icon: User, label: "Full Name", value: profile?.full_name ?? "--" },
                    { icon: Mail, label: "Email Address", value: profile?.email ? `${profile.email.slice(0, 3)}***${profile.email.slice(profile.email.indexOf("@"))}` : "--" },
                    { icon: User, label: "Username", value: profile?.customer_ref ?? state.username ?? "--" },
                    { icon: Building2, label: "Customer Reference", value: profile?.customer_ref ?? "--" },
                  ].map(({ icon: Icon, label, value }) => (
                    <div key={label} className="flex items-center gap-4 rounded-lg bg-surface-container-low p-3">
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/10">
                        <Icon className="h-4 w-4 text-primary" />
                      </div>
                      <div>
                        <p className="text-[11px] font-semibold uppercase tracking-wider text-on-surface-variant">{label}</p>
                        <p className="mt-0.5 text-sm font-medium text-on-surface">{value}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Accounts */}
              <div className="rounded-2xl border border-outline-variant bg-white p-6 shadow-sm">
                <h2 className="font-headline mb-4 text-base font-bold text-on-surface">Linked Accounts</h2>
                <div className="space-y-3">
                  {accounts.map((acc) => (
                    <div key={acc.account_id} className="flex items-center gap-4 rounded-lg border border-outline-variant p-4">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10">
                        <CreditCard className="h-5 w-5 text-primary" />
                      </div>
                      <div className="flex-1">
                        <p className="text-sm font-semibold capitalize text-on-surface">{acc.account_type ?? "Account"}</p>
                        <p className="font-mono text-xs text-on-surface-variant">{acc.masked_account_number}</p>
                      </div>
                      <div className="text-right">
                        <p className="font-headline text-base font-bold text-primary">
                          {formatCurrency(acc.balance, acc.currency)}
                        </p>
                        <p className="text-[10px] capitalize text-on-surface-variant">{acc.status}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Security link */}
              <button
                type="button"
                onClick={() => navigate("/security", { state: { username: displayName } })}
                className="flex w-full items-center gap-3 rounded-xl border border-outline-variant bg-white p-4 text-left shadow-sm transition-all hover:border-primary/40 hover:bg-primary/5"
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10">
                  <Shield className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-on-surface">Security Settings</p>
                  <p className="text-xs text-on-surface-variant">Manage trusted devices and active sessions</p>
                </div>
                <span className="ml-auto text-xs font-bold text-primary">→</span>
              </button>
            </div>
          </div>
        )}
      </main>

      <Footer />
    </div>
  );
}
