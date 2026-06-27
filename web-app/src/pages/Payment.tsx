import { CogniGuard } from "@cogniguard/behavior-sdk";
import { type FormEvent, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { type PaymentScoreResponse, getSessionToken, scorePayment } from "../api";
import CoercionCheck from "../components/CoercionCheck";
import CoolingNotice from "../components/CoolingNotice";
import ManualAmountEntry from "../components/ManualAmountEntry";
import RiskBadge from "../components/RiskBadge";

interface PaymentLocationState {
  username?: string;
  // Set by StepUp.tsx when a pending transaction's step-up resolves -- picks back up
  // exactly where the transfer left off (same risk/controls, action now "allow").
  resolvedPayment?: PaymentScoreResponse;
}

export default function Payment() {
  const navigate = useNavigate();
  const location = useLocation();
  const locationState = location.state as PaymentLocationState | null;

  const [amount, setAmount] = useState("");
  const [beneficiaryVpa, setBeneficiaryVpa] = useState("");
  const [response, setResponse] = useState<PaymentScoreResponse | null>(null);
  const [confirmedManualAmount, setConfirmedManualAmount] = useState(false);
  const [coercionAnswered, setCoercionAnswered] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (locationState?.resolvedPayment) {
      setResponse(locationState.resolvedPayment);
    }
    // Only resume once, on the navigation back from /step-up -- not on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locationState?.resolvedPayment]);

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
      if (body.action === "verify" && body.step_up) {
        navigate("/step-up", {
          state: {
            challenge: body.step_up,
            requiredFactors: body.required_factors,
            username: locationState?.username,
            entityType: "transaction",
          },
        });
        return;
      }
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
    <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-6 shadow-sm">
      <h1 className="font-headline text-xl font-bold text-on-surface">Transfer money</h1>
      <form className="mt-4 space-y-3" onSubmit={submit}>
        <div>
          <label className="block text-sm text-on-surface-variant" htmlFor="beneficiary">
            Beneficiary VPA
          </label>
          <input
            id="beneficiary"
            className="mt-1 w-full rounded border border-outline-variant px-2 py-1 focus:border-primary focus:outline-none"
            value={beneficiaryVpa}
            onChange={(e) => setBeneficiaryVpa(e.target.value)}
            placeholder="payee@upi"
          />
        </div>
        <div>
          <label className="block text-sm text-on-surface-variant" htmlFor="amount">
            Amount (₹)
          </label>
          <input
            id="amount"
            type="number"
            className="mt-1 w-full rounded border border-outline-variant px-2 py-1 focus:border-primary focus:outline-none"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </div>
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded bg-primary px-3 py-2 font-semibold text-on-primary hover:bg-primary-container disabled:opacity-50"
        >
          {busy ? "Scoring..." : "Send"}
        </button>
      </form>

      {error && <p className="mt-3 text-sm text-secondary">{error}</p>}

      {response && (
        <div className="mt-4 space-y-3">
          <div className="flex items-center gap-2">
            <RiskBadge band={response.risk_band} score={response.risk_score} />
            <span className="text-sm text-on-surface-variant">action: {response.action}</span>
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
