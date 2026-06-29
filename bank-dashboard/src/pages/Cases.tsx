import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { type CaseOut, listCases } from "../api";
import CaseDrawer from "../components/CaseDrawer";
import { connectSocFeed, isCaseOpenedEvent } from "../ws";

const SEVERITY_STYLES: Record<string, string> = {
  critical: "bg-band-very-high-bg text-band-very-high",
  high: "bg-band-high-bg text-band-high",
  medium: "bg-band-medium-bg text-band-medium",
  low: "bg-band-low-bg text-band-low",
};

const BAND_STYLES: Record<string, string> = {
  very_high: "bg-band-very-high-bg text-band-very-high",
  high: "bg-band-high-bg text-band-high",
  medium: "bg-band-medium-bg text-band-medium",
  low: "bg-band-low-bg text-band-low",
};

const STATUS_STYLES: Record<string, string> = {
  open: "bg-soc-warning-light text-soc-warning",
  investigating: "bg-soc-primary-light text-soc-primary",
  confirmed_fraud: "bg-soc-danger-light text-soc-danger",
  false_positive: "bg-soc-success-light text-soc-success",
  closed: "bg-soc-bg text-soc-muted",
};

export default function Cases() {
  const [cases, setCases] = useState<CaseOut[]>([]);
  const [selected, setSelected] = useState<CaseOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [wsStatus, setWsStatus] = useState<"open" | "closed">("closed");
  // Debounce rapid bursts (e.g. two cases created within ms of each other).
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(() => {
    setLoading(true);
    listCases({ limit: 100 })
      .then(({ body }) => setCases(body))
      .catch(() => undefined)
      .finally(() => setLoading(false));
  }, []);

  // Silent refresh — no loading spinner, used by the real-time WS path so the
  // table doesn't flash while new cases stream in.
  const silentRefresh = useCallback(() => {
    listCases({ limit: 100 })
      .then(({ body }) => setCases(body))
      .catch(() => undefined);
  }, []);

  // Initial load.
  useEffect(() => { refresh(); }, [refresh]);

  // Real-time case updates via WebSocket.
  useEffect(() => {
    const disconnect = connectSocFeed((event) => {
      if (!isCaseOpenedEvent(event)) return;
      // Debounce: if multiple cases arrive within 300 ms, only refresh once.
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        silentRefresh();
        debounceRef.current = null;
      }, 300);
    }, setWsStatus);

    return () => {
      disconnect();
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [silentRefresh]);

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-headline text-2xl font-bold text-soc-text">Case Management</h1>
          <div className="mt-0.5 flex items-center gap-2">
            <p className="text-sm text-soc-muted">{cases.length} case{cases.length !== 1 ? "s" : ""} total</p>
            <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${wsStatus === "open" ? "bg-soc-success-light text-soc-success" : "bg-soc-bg text-soc-muted"}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${wsStatus === "open" ? "bg-soc-success animate-pulse" : "bg-soc-muted"}`} />
              {wsStatus === "open" ? "Live" : "Offline"}
            </span>
          </div>
        </div>
        <button
          type="button"
          onClick={refresh}
          className="flex items-center gap-1.5 rounded-lg border border-soc-border bg-soc-surface px-3 py-2 text-sm font-medium text-soc-muted transition-colors hover:border-soc-primary hover:text-soc-primary"
        >
          <RefreshCw className="h-4 w-4" />
          <span>Refresh</span>
        </button>
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-soc-border bg-soc-elevated text-[11px] font-semibold uppercase tracking-wider text-soc-muted">
                <th className="px-5 py-3 text-left">Case ID</th>
                <th className="px-5 py-3 text-left">Status</th>
                <th className="px-5 py-3 text-left">Severity</th>
                <th className="px-5 py-3 text-left">Risk Band</th>
                <th className="px-5 py-3 text-right">Score</th>
                <th className="px-5 py-3 text-left">Assigned To</th>
                <th className="px-5 py-3 text-right">Updated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-soc-border">
              {loading && (
                <tr>
                  <td colSpan={7} className="px-5 py-10 text-center text-sm text-soc-muted">Loading cases…</td>
                </tr>
              )}
              {!loading && cases.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-5 py-10 text-center text-sm text-soc-muted">No cases found.</td>
                </tr>
              )}
              {cases.map((c, i) => (
                <tr
                  key={c.case_id}
                  className={`cursor-pointer transition-colors hover:bg-soc-primary-light/30 ${i % 2 === 0 ? "" : "bg-soc-elevated/50"}`}
                  onClick={() => setSelected(c)}
                >
                  <td className="px-5 py-3.5">
                    <span className="font-mono text-xs font-medium text-soc-text">{c.case_id.slice(0, 12)}…</span>
                  </td>
                  <td className="px-5 py-3.5">
                    <span className={`inline-block rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${STATUS_STYLES[c.status] ?? "bg-soc-bg text-soc-muted"}`}>
                      {c.status.replace("_", " ")}
                    </span>
                  </td>
                  <td className="px-5 py-3.5">
                    {c.severity ? (
                      <span className={`inline-block rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${SEVERITY_STYLES[c.severity] ?? "bg-soc-bg text-soc-muted"}`}>
                        {c.severity}
                      </span>
                    ) : (
                      <span className="text-soc-muted">—</span>
                    )}
                  </td>
                  <td className="px-5 py-3.5">
                    {c.risk_band ? (
                      <span className={`inline-block rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${BAND_STYLES[c.risk_band] ?? "bg-soc-bg text-soc-muted"}`}>
                        {c.risk_band.replace("_", " ")}
                      </span>
                    ) : (
                      <span className="text-soc-muted">—</span>
                    )}
                  </td>
                  <td className="px-5 py-3.5 text-right font-mono text-xs text-soc-text">
                    {c.final_risk_score != null ? c.final_risk_score.toFixed(1) : "—"}
                  </td>
                  <td className="px-5 py-3.5 text-sm text-soc-muted">{c.assigned_to ?? "—"}</td>
                  <td className="px-5 py-3.5 text-right font-mono text-xs text-soc-muted">
                    {c.updated_at ? new Date(c.updated_at).toLocaleDateString("en-IN") : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {selected && (
        <CaseDrawer
          caseItem={selected}
          onClose={() => setSelected(null)}
          onUpdated={(updated) => {
            setCases((prev) => prev.map((c) => (c.case_id === updated.case_id ? updated : c)));
            setSelected(null);
          }}
          latestScoreId={selected.score_id ?? null}
        />
      )}
    </div>
  );
}
