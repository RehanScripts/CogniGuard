import { useEffect, useState } from "react";

import { type DriftReportOut, type ModelOut, getDrift, listModels } from "../api";

// Read-only champion/challenger + drift view (Implementation.md Phase 12). Promote/
// rollback stay API/CLI-only by design (see the Phase 12 plan's scope decision) -- this
// panel never mutates model_registry, only displays it.
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
    return <p className="text-sm text-red-500">Failed to load model governance data.</p>;
  }

  return (
    <div className="space-y-4 text-sm">
      <div>
        <h3 className="mb-1 font-medium text-gray-600">Registered models</h3>
        {models.length === 0 ? (
          <p className="text-gray-400">No models registered yet.</p>
        ) : (
          <table className="w-full text-left">
            <thead className="text-xs text-gray-500">
              <tr>
                <th className="pr-2">Model</th>
                <th className="pr-2">Version</th>
                <th className="pr-2">Stage</th>
                <th>Deployed</th>
              </tr>
            </thead>
            <tbody>
              {models.flatMap((m) =>
                m.versions.map((v) => (
                  <tr key={v.model_id}>
                    <td className="pr-2">{m.model_name}</td>
                    <td className="pr-2">{v.version}</td>
                    <td className="pr-2">{v.stage}</td>
                    <td>{v.deployed_at ? new Date(v.deployed_at).toLocaleString() : "—"}</td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        )}
      </div>

      <div>
        <h3 className="mb-1 font-medium text-gray-600">Score drift (live vs. reference window)</h3>
        {drift === null ? (
          <p className="text-gray-400">Loading…</p>
        ) : (
          <table className="w-full text-left">
            <thead className="text-xs text-gray-500">
              <tr>
                <th className="pr-2">Column</th>
                <th className="pr-2">PSI</th>
                <th className="pr-2">KS stat</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(drift.columns).map(([column, report]) => (
                <tr key={column}>
                  <td className="pr-2">{column}</td>
                  <td className="pr-2">{report.psi?.toFixed(3) ?? "—"}</td>
                  <td className="pr-2">{report.ks_stat?.toFixed(3) ?? "—"}</td>
                  <td className={report.breached ? "text-red-600" : "text-gray-500"}>
                    {report.skipped
                      ? "insufficient samples"
                      : report.breached
                        ? "breached"
                        : "stable"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {drift && drift.outcome.precision !== null && (
          <p className="mt-2 text-xs text-gray-500">
            Outcome precision (resolved cases): {(drift.outcome.precision * 100).toFixed(1)}% (
            {drift.outcome.n_confirmed_fraud} confirmed / {drift.outcome.n_resolved} resolved)
          </p>
        )}
      </div>
    </div>
  );
}
