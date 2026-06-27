import { ArrowUpRight, CheckCircle2, UserCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import {
  type BeneficiaryOut,
  type TransactionOut,
  getSessionToken,
  listBeneficiaries,
  listTransactions,
} from "../api";
import AppHeader from "../components/AppHeader";
import Footer from "../components/Footer";

function formatAmount(amount: number | null, currency: string | null): string {
  if (amount === null) return "--";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: currency ?? "INR",
    maximumFractionDigits: 2,
  }).format(amount);
}

export default function Transactions() {
  const navigate = useNavigate();
  const location = useLocation();
  const username = (location.state as { username?: string } | null)?.username ?? "genuine";

  const [transactions, setTransactions] = useState<TransactionOut[]>([]);
  const [beneficiaries, setBeneficiaries] = useState<BeneficiaryOut[]>([]);
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
        const [txnRes, benefRes] = await Promise.all([
          listTransactions(token),
          listBeneficiaries(token),
        ]);
        if (cancelled) return;
        if (txnRes.status === 200) setTransactions(txnRes.body);
        if (benefRes.status === 200) setBeneficiaries(benefRes.body);
      } catch {
        if (!cancelled) setError("Could not load transaction history.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  return (
    <div className="flex min-h-screen flex-col bg-background-custom">
      <AppHeader username={username} />
      <div className="mx-auto mt-8 w-full max-w-md flex-1 px-4">
        <button
          type="button"
          className="mb-4 text-sm font-medium text-primary"
          onClick={() => navigate("/dashboard", { state: { username } })}
        >
          ← Back to dashboard
        </button>

        <div className="overflow-hidden rounded-xl border border-outline-variant bg-surface-container-lowest shadow-sm">
          <h1 className="font-headline px-5 pt-5 text-xl font-bold text-on-surface">Transaction history</h1>
          {loading && <p className="px-5 pb-5 pt-2 text-sm text-on-surface-variant">Loading...</p>}
          {error && <p className="px-5 pb-5 pt-2 text-sm text-secondary">{error}</p>}
          {!loading && !error && transactions.length === 0 && (
            <p className="px-5 pb-5 pt-2 text-sm text-on-surface-variant">No transactions yet.</p>
          )}
          {transactions.length > 0 && (
            <div className="mt-3 divide-y divide-outline-variant">
              {transactions.map((txn) => (
                <div key={txn.transaction_id} className="flex items-center justify-between gap-3 px-5 py-3.5 transition-colors hover:bg-slate-50">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-rose-50 text-rose-500">
                      <ArrowUpRight className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="text-xs font-bold text-on-surface">
                        {txn.beneficiary_name ?? txn.masked_beneficiary_account ?? "--"}
                      </p>
                      <p className="mt-0.5 text-[10px] text-on-surface-variant">
                        {txn.transfer_type} &middot; {txn.status} &middot; {txn.initiated_at ?? "--"}
                      </p>
                    </div>
                  </div>
                  <p className="text-sm font-bold text-secondary">{formatAmount(txn.amount, txn.currency)}</p>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="mt-4 overflow-hidden rounded-xl border border-outline-variant bg-surface-container-lowest shadow-sm">
          <div className="flex items-center justify-between px-5 pt-5">
            <h2 className="font-headline text-lg font-bold text-on-surface">Beneficiaries</h2>
            {beneficiaries.length > 0 && <UserCheck className="h-4 w-4 text-primary" />}
          </div>
          {!loading && !error && beneficiaries.length === 0 && (
            <p className="px-5 pb-5 pt-2 text-sm text-on-surface-variant">No saved beneficiaries.</p>
          )}
          {beneficiaries.length > 0 && (
            <div className="mt-3 divide-y divide-outline-variant">
              {beneficiaries.map((b) => (
                <div key={b.beneficiary_id} className="flex items-center justify-between gap-3 px-5 py-3.5">
                  <div className="flex items-center gap-3">
                    <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">
                      {(b.name ?? "--").slice(0, 2).toUpperCase()}
                    </div>
                    <span className="text-sm text-on-surface">
                      {b.name} ({b.masked_account_number})
                    </span>
                  </div>
                  <span className={`flex items-center gap-1 text-xs font-semibold ${b.is_verified ? "text-emerald-600" : "text-on-surface-variant"}`}>
                    {b.is_verified && <CheckCircle2 className="h-3.5 w-3.5" />}
                    <span>{b.is_verified ? "Verified" : "Unverified"}</span>
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      <Footer />
    </div>
  );
}
