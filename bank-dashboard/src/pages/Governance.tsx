import { useEffect, useState } from "react";

import { type EventOut, type FactoryResetOut, factoryReset, listEvents } from "../api";
import DriftPanel from "../components/DriftPanel";
import LatencyHistogram from "../components/LatencyHistogram";

const LOGIN_BUDGET_MS = 300;
const PAYMENT_BUDGET_MS = 500;

export default function Governance() {
  const [events, setEvents] = useState<EventOut[]>([]);
  const [resetLoading, setResetLoading] = useState(false);
  const [resetResult, setResetResult] = useState<FactoryResetOut | null>(null);
  const [resetError, setResetError] = useState<string | null>(null);

  useEffect(() => {
    listEvents({ limit: 200 })
      .then(({ body }) => setEvents(body))
      .catch(() => undefined);
  }, []);

  const loginLatencies = events
    .filter((e) => e.entity_type === "login" && e.latency_ms != null)
    .map((e) => e.latency_ms as number);
  const txnLatencies = events
    .filter((e) => e.entity_type === "transaction" && e.latency_ms != null)
    .map((e) => e.latency_ms as number);

  async function handleFactoryReset() {
    if (!window.confirm(
      "DANGER: This will permanently delete ALL users, sessions, behavioral baselines, and demo data.\n\n" +
      "The SOC analysts and models are preserved.\n\nProceed?"
    )) return;
    setResetLoading(true);
    setResetResult(null);
    setResetError(null);
    try {
      const res = await factoryReset();
      if (res.status === 200) {
        setResetResult(res.body);
      } else {
        setResetError((res.body as { detail?: string }).detail ?? "Factory reset failed.");
      }
    } catch {
      setResetError("Network error — factory reset did not complete.");
    } finally {
      setResetLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="font-headline text-2xl font-bold text-soc-text">Model Governance</h1>
        <p className="mt-0.5 text-sm text-soc-muted">Latency budgets, drift monitors, and champion/challenger status</p>
      </div>

      {/* Latency cards */}
      <div className="grid gap-5 md:grid-cols-2">
        <div className="card overflow-hidden">
          <div className="card-header flex items-center justify-between">
            <h2 className="font-semibold text-soc-text">Login Latency</h2>
            <span className="rounded-full bg-soc-primary-light px-2.5 py-0.5 text-[11px] font-bold text-soc-primary">
              p95 budget {LOGIN_BUDGET_MS} ms
            </span>
          </div>
          <div className="p-5">
            <LatencyHistogram latenciesMs={loginLatencies} budgetMs={LOGIN_BUDGET_MS} />
          </div>
        </div>

        <div className="card overflow-hidden">
          <div className="card-header flex items-center justify-between">
            <h2 className="font-semibold text-soc-text">Payment Latency</h2>
            <span className="rounded-full bg-soc-primary-light px-2.5 py-0.5 text-[11px] font-bold text-soc-primary">
              p95 budget {PAYMENT_BUDGET_MS} ms
            </span>
          </div>
          <div className="p-5">
            <LatencyHistogram latenciesMs={txnLatencies} budgetMs={PAYMENT_BUDGET_MS} />
          </div>
        </div>
      </div>

      {/* Drift panel */}
      <div className="card overflow-hidden">
        <div className="card-header">
          <h2 className="font-semibold text-soc-text">Champion / Challenger &amp; Drift</h2>
        </div>
        <div className="p-5">
          <DriftPanel />
        </div>
      </div>

      {/* Danger zone */}
      <div className="card overflow-hidden border border-soc-danger-light">
        <div className="card-header bg-soc-danger-light">
          <h2 className="font-semibold text-soc-danger">Danger Zone</h2>
        </div>
        <div className="p-5 space-y-3">
          <p className="text-sm text-soc-muted">
            Factory reset deletes all users, sessions, behavioral baselines, devices, transactions,
            cases, and audit logs. Models and SOC analyst accounts are preserved. After reset the
            next interaction must be Sign Up — enrollment starts from 0/10 sessions.
          </p>
          {resetResult && (
            <div className="rounded-lg border border-green-300 bg-green-50 px-4 py-3 text-xs text-green-800">
              Reset complete. Tables wiped: {resetResult.tables_truncated.join(", ")}. Redis: {resetResult.redis}.
            </div>
          )}
          {resetError && (
            <p className="rounded-lg border border-soc-danger-light bg-soc-danger-light px-3 py-2 text-xs font-medium text-soc-danger">
              {resetError}
            </p>
          )}
          <button
            type="button"
            disabled={resetLoading}
            onClick={() => void handleFactoryReset()}
            className="rounded-lg border border-soc-danger bg-soc-danger px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {resetLoading ? "Resetting…" : "Factory Reset"}
          </button>
        </div>
      </div>
    </div>
  );
}
