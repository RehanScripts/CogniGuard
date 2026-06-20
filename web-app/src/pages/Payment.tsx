import { CogniGuard } from "@cogniguard/behavior-sdk";
import { type FormEvent, useState } from "react";

import { type PaymentScoreResponse, getSessionToken, scorePayment } from "../api";
import CoercionCheck from "../components/CoercionCheck";
import CoolingNotice from "../components/CoolingNotice";
import ManualAmountEntry from "../components/ManualAmountEntry";
import RiskBadge from "../components/RiskBadge";

export default function Payment() {
  const [amount, setAmount] = useState("");
  const [beneficiaryVpa, setBeneficiaryVpa] = useState("");
  const [response, setResponse] = useState<PaymentScoreResponse | null>(null);
  const [confirmedManualAmount, setConfirmedManualAmount] = useState(false);
  const [coercionAnswered, setCoercionAnswered] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setResponse(null);
    setConfirmedManualAmount(false);
    setCoercionAnswered(false);
    const token = getSessionToken();
    if (!token) {
      setError("Session expired -- please log in again.");
      return;
    }
    setBusy(true);
    try {
      const behavior = await CogniGuard.collect("TRANSFER");
      const { body } = await scorePayment(token, {
        amount: Number(amount),
        beneficiary_vpa: beneficiaryVpa,
        transfer_type: "UPI",
        channel: "web",
        behavior,
      });
      setResponse(body);
    } catch {
      setError("Could not reach CogniGuard. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const controls = response?.txn_controls ?? null;
  const needsCoercionCheck = Boolean(controls?.coercion_check) && !coercionAnswered;
  const needsManualAmount = Boolean(controls?.manual_amount) && !confirmedManualAmount;

  return (
    <div className="rounded border p-6 shadow-sm">
      <h1 className="text-xl font-semibold">Transfer money</h1>
      <form className="mt-4 space-y-3" onSubmit={submit}>
        <div>
          <label className="block text-sm text-gray-600" htmlFor="beneficiary">
            Beneficiary VPA
          </label>
          <input
            id="beneficiary"
            className="mt-1 w-full rounded border px-2 py-1"
            value={beneficiaryVpa}
            onChange={(e) => setBeneficiaryVpa(e.target.value)}
            placeholder="payee@upi"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-600" htmlFor="amount">
            Amount (₹)
          </label>
          <input
            id="amount"
            type="number"
            className="mt-1 w-full rounded border px-2 py-1"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </div>
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded bg-blue-600 px-3 py-2 text-white disabled:opacity-50"
        >
          {busy ? "Scoring..." : "Send"}
        </button>
      </form>

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      {response && (
        <div className="mt-4 space-y-3">
          <div className="flex items-center gap-2">
            <RiskBadge band={response.risk_band} score={response.risk_score} />
            <span className="text-sm text-gray-600">action: {response.action}</span>
          </div>

          {needsCoercionCheck && (
            <CoercionCheck
              amount={Number(amount)}
              onConfirm={() => setCoercionAnswered(true)}
              onCancel={() => setResponse(null)}
            />
          )}

          {!needsCoercionCheck && needsManualAmount && (
            <ManualAmountEntry
              expectedAmount={Number(amount)}
              onConfirmed={() => setConfirmedManualAmount(true)}
            />
          )}

          {!needsCoercionCheck && !needsManualAmount && controls?.cooling_until && (
            <CoolingNotice coolingUntil={controls.cooling_until} />
          )}
        </div>
      )}
    </div>
  );
}
