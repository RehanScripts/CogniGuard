import { useEffect, useState } from "react";

import { type EventOut, listEvents } from "../api";
import DriftPanel from "../components/DriftPanel";
import LatencyHistogram from "../components/LatencyHistogram";

const LOGIN_BUDGET_MS = 300;
const PAYMENT_BUDGET_MS = 500;

export default function Governance() {
  const [events, setEvents] = useState<EventOut[]>([]);

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

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Model governance</h1>

      <div className="rounded border p-3">
        <h2 className="mb-2 text-sm font-medium text-gray-600">
          Login latency (p95 budget {LOGIN_BUDGET_MS}ms)
        </h2>
        <LatencyHistogram latenciesMs={loginLatencies} budgetMs={LOGIN_BUDGET_MS} />
      </div>

      <div className="rounded border p-3">
        <h2 className="mb-2 text-sm font-medium text-gray-600">
          Payment latency (p95 budget {PAYMENT_BUDGET_MS}ms)
        </h2>
        <LatencyHistogram latenciesMs={txnLatencies} budgetMs={PAYMENT_BUDGET_MS} />
      </div>

      <div className="rounded border p-3">
        <h2 className="mb-2 text-sm font-medium text-gray-600">Champion / challenger + drift</h2>
        <DriftPanel />
      </div>
    </div>
  );
}
