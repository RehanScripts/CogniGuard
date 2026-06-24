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
    <div className="min-h-screen bg-background-custom">
      <AppHeader username={username} />
      <div className="mx-auto mt-8 max-w-md px-4">
        <button
          type="button"
          className="mb-4 text-sm font-medium text-primary"
          onClick={() => navigate("/dashboard", { state: { username } })}
        >
          ← Back to dashboard
        </button>

        <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-6 shadow-sm">
          <h1 className="font-headline text-xl font-bold text-on-surface">Transaction history</h1>
          {loading && <p className="mt-2 text-sm text-on-surface-variant">Loading...</p>}
          {error && <p className="mt-2 text-sm text-secondary">{error}</p>}
          {!loading && !error && transactions.length === 0 && (
            <p className="mt-2 text-sm text-on-surface-variant">No transactions yet.</p>
          )}
          <ul className="mt-3 space-y-2">
            {transactions.map((txn) => (
              <li key={txn.transaction_id} className="border-t border-outline-variant pt-2 first:border-t-0 first:pt-0">
                <div className="flex justify-between text-sm">
                  <span className="text-on-surface">{txn.beneficiary_name ?? txn.masked_beneficiary_account ?? "--"}</span>
                  <span className="font-medium text-secondary">{formatAmount(txn.amount, txn.currency)}</span>
                </div>
                <p className="text-xs text-on-surface-variant">
                  {txn.transfer_type} &middot; {txn.status} &middot; {txn.initiated_at ?? "--"}
                </p>
              </li>
            ))}
          </ul>
        </div>

        <div className="mt-4 rounded-xl border border-outline-variant bg-surface-container-lowest p-6 shadow-sm">
          <h2 className="font-headline text-lg font-bold text-on-surface">Beneficiaries</h2>
          {!loading && !error && beneficiaries.length === 0 && (
            <p className="mt-2 text-sm text-on-surface-variant">No saved beneficiaries.</p>
          )}
          <ul className="mt-3 space-y-2">
            {beneficiaries.map((b) => (
              <li key={b.beneficiary_id} className="flex justify-between border-t border-outline-variant pt-2 text-sm first:border-t-0 first:pt-0">
                <span className="text-on-surface">
                  {b.name} ({b.masked_account_number})
                </span>
                <span className="text-on-surface-variant">{b.is_verified ? "Verified" : "Unverified"}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
