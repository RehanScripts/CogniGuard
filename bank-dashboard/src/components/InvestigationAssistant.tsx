import { useState } from "react";

import { type InvestigationResultOut, investigateCase } from "../api";

interface Props {
  caseId: string;
}

export default function InvestigationAssistant({ caseId }: Props) {
  const [result, setResult] = useState<InvestigationResultOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleInvestigate() {
    setLoading(true);
    setError(null);
    try {
      const res = await investigateCase(caseId);
      if (res.status === 200) {
        setResult(res.body);
      } else {
        setError((res.body as { detail?: string }).detail ?? "Investigation unavailable.");
      }
    } catch {
      setError("Failed to reach investigation service.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-5 text-xs">
      {!result && (
        <button
          type="button"
          disabled={loading}
          onClick={() => void handleInvestigate()}
          className="rounded-lg border border-soc-primary bg-soc-primary-light px-4 py-2 font-semibold text-soc-primary transition-colors hover:bg-soc-primary hover:text-white disabled:opacity-50"
        >
          {loading ? "Investigating…" : "Investigate with AI"}
        </button>
      )}
      {error && (
        <p className="mt-2 rounded-lg border border-soc-danger-light bg-soc-danger-light px-3 py-2 font-medium text-soc-danger">
          {error}
        </p>
      )}
      {result && (
        <div className="mt-3 space-y-3 rounded-xl border border-soc-border bg-soc-elevated p-4">
          <div className="flex items-center justify-between">
            <p className="font-bold text-soc-text">AI Investigation</p>
            <span className="rounded-full bg-soc-primary-light px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-soc-primary">
              {result.provider}
            </span>
          </div>
          <p className="leading-relaxed text-soc-text">{result.summary}</p>
          {result.risk_factors.length > 0 && (
            <div>
              <p className="mb-1.5 font-semibold text-soc-muted">Risk Factors</p>
              <ul className="space-y-1 pl-4 text-soc-text" style={{ listStyleType: "disc" }}>
                {result.risk_factors.map((f, i) => (
                  <li key={i}>{f}</li>
                ))}
              </ul>
            </div>
          )}
          {result.recommendation && (
            <div className="rounded-lg border border-soc-border bg-soc-surface p-3">
              <p className="mb-1 font-semibold text-soc-primary">Recommendation</p>
              <p className="leading-relaxed text-soc-text">{result.recommendation}</p>
            </div>
          )}
          {result.generated_at && (
            <p className="text-[10px] text-soc-muted">
              Generated {new Date(result.generated_at).toLocaleString("en-IN")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
