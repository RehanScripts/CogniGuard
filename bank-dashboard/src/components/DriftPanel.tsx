import { useEffect, useState } from "react";

import { type DriftReportOut, type ModelOut, getDrift, listModels } from "../api";

// Read-only champion/challenger + drift view (Implementation.md Phase 12). Promote/
// rollback stay API/CLI-only by design (see the Phase 12 plan's scope decision) -- this
// panel never mutates model_registry, only displays it.

const STAGE_STYLES: Record<string, string> = {
  production: "bg-band-low-bg text-band-low",
  staging: "bg-soc-primary-light text-soc-primary",
  archived: "bg-soc-elevated text-soc-muted",
};

export default function DriftPanel() {
  const [models, setModels] = useState<ModelOut[]>([]);
  const [drift, setDrift] = useState<DriftReportOut | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    Promise.all([listModels(), getDrift()])
      .then(([modelsRes, driftRes]) => {
        setModels(modelsRes.body);
        setDrift(driftRes.body);
      })
      .catch(() => setError(true));
  }, []);

  if (error) {
    return (
      <p className="rounded-lg border border-soc-danger-light bg-soc-danger-light px-3 py-2 text-sm font-medium text-soc-danger">
        Failed to load model governance data.
      </p>
    );
  }

  return (
    <div className="space-y-5 text-sm">
      {/* Registered models */}
      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-soc-muted">Registered Models</h3>
        {models.length === 0 ? (
          <p className="text-soc-muted">No models registered yet.</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-soc-border">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-soc-border bg-soc-elevated">
                <tr>
                  {["Model", "Version", "Stage", "Deployed"].map((h) => (
                    <th key={h} className="px-4 py-2.5 font-semibold uppercase tracking-wider text-soc-muted">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-soc-border">
                {models.flatMap((m) =>
                  m.versions.map((v) => (
                    <tr key={v.model_id} className="hover:bg-soc-elevated/50">
                      <td className="px-4 py-2.5 font-mono font-medium text-soc-text">{m.model_name}</td>
                      <td className="px-4 py-2.5 font-mono text-soc-muted">{v.version}</td>
                      <td className="px-4 py-2.5">
                        <span className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${(v.stage ? STAGE_STYLES[v.stage] : null) ?? "bg-soc-elevated text-soc-muted"}`}>
                          {v.stage}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 font-mono text-soc-muted">
                        {v.deployed_at ? new Date(v.deployed_at).toLocaleString("en-IN") : "—"}
                      </td>
                    </tr>
                  )),
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Score drift */}
      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-soc-muted">Score Drift (Live vs. Reference Window)</h3>
        {drift === null ? (
          <div className="flex items-center gap-2 text-soc-muted">
            <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-soc-primary border-t-transparent" />
            <span className="text-xs">Loading…</span>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-soc-border">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-soc-border bg-soc-elevated">
                <tr>
                  {["Column", "PSI", "KS stat", "Status"].map((h) => (
                    <th key={h} className="px-4 py-2.5 font-semibold uppercase tracking-wider text-soc-muted">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-soc-border">
                {Object.entries(drift.columns).map(([column, report]) => (
                  <tr key={column} className="hover:bg-soc-elevated/50">
                    <td className="px-4 py-2.5 font-mono text-soc-text">{column}</td>
                    <td className="px-4 py-2.5 font-mono text-soc-muted">{report.psi?.toFixed(3) ?? "—"}</td>
                    <td className="px-4 py-2.5 font-mono text-soc-muted">{report.ks_stat?.toFixed(3) ?? "—"}</td>
                    <td className={`px-4 py-2.5 font-semibold ${report.breached ? "text-soc-danger" : "text-soc-success"}`}>
                      {report.skipped
                        ? <span className="text-soc-muted font-normal">insufficient samples</span>
                        : report.breached
                          ? "breached"
                          : "stable"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {drift && drift.outcome.precision !== null && (
          <p className="mt-2 text-xs text-soc-muted">
            Outcome precision (resolved cases):{" "}
            <span className="font-semibold text-soc-text">
              {(drift.outcome.precision * 100).toFixed(1)}%
            </span>
            {" "}({drift.outcome.n_confirmed_fraud} confirmed / {drift.outcome.n_resolved} resolved)
          </p>
        )}
      </div>
    </div>
  );
}
