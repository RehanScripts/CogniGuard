import { useState } from "react";

import { type ShapExplanationOut, explainScore } from "../api";

interface Props {
  scoreId: string;
}

// Lightweight inline markdown renderer: bold (**text**), newlines → paragraphs.
function MarkdownText({ text }: { text: string }) {
  const paragraphs = text.split(/\n\n+/);
  return (
    <div className="space-y-2">
      {paragraphs.map((para, pi) => {
        const lines = para.split(/\n/);
        return (
          <div key={pi} className="space-y-0.5">
            {lines.map((line, li) => (
              <p key={li} className="text-sm leading-relaxed text-soc-text">
                <InlineBold text={line} />
              </p>
            ))}
          </div>
        );
      })}
    </div>
  );
}

function InlineBold({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("**") && part.endsWith("**")) {
          return (
            <strong key={i} className="font-semibold text-soc-primary">
              {part.slice(2, -2)}
            </strong>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </>
  );
}

export default function SHAPExplainer({ scoreId }: Props) {
  const [result, setResult] = useState<ShapExplanationOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [blocked, setBlocked] = useState(false);
  const [surveillance, setSurveillance] = useState(false);

  async function handleExplain() {
    setLoading(true);
    setError(null);
    try {
      const res = await explainScore(scoreId);
      if (res.status === 200) {
        setResult(res.body);
      } else {
        setError((res.body as { detail?: string }).detail ?? "Explanation unavailable.");
      }
    } catch {
      setError("Failed to fetch explanation.");
    } finally {
      setLoading(false);
    }
  }

  const maxAbs = result
    ? Math.max(...result.top_features.map((f) => Math.abs(f.shap_value)), 0.001)
    : 0;
  const hasRealShap = maxAbs >= 0.01;

  return (
    <div className="p-5 text-xs">
      {!result && (
        <button
          type="button"
          disabled={loading}
          onClick={() => void handleExplain()}
          className="rounded-lg border border-soc-border bg-soc-elevated px-4 py-2 font-semibold text-soc-text transition-colors hover:border-soc-primary hover:text-soc-primary disabled:opacity-50"
        >
          {loading ? "Explaining…" : "Explain Score (SHAP + AI)"}
        </button>
      )}
      {error && (
        <p className="mt-2 rounded-lg border border-soc-danger-light bg-soc-danger-light px-3 py-2 font-medium text-soc-danger">
          {error}
        </p>
      )}
      {result && (
        <div className="mt-3 space-y-2">
          {hasRealShap ? (
            <>
              <p className="mb-3 text-soc-muted">
                Model: <span className="font-medium text-soc-text">{result.model_version ?? "unknown"}</span>
                {" · "}Top {result.top_features.length} features
              </p>
              {result.top_features.map((f) => (
                <div key={f.feature} className="flex items-center gap-2">
                  <span className="w-36 truncate font-medium text-soc-text" title={f.feature}>
                    {f.feature}
                  </span>
                  <div className="relative flex h-4 flex-1 items-center rounded bg-soc-elevated">
                    {f.shap_value >= 0 ? (
                      <div
                        className="h-2 rounded-r bg-soc-danger"
                        style={{ width: `${(f.shap_value / maxAbs) * 100}%` }}
                      />
                    ) : (
                      <div
                        className="ml-auto h-2 rounded-l bg-soc-primary"
                        style={{ width: `${(Math.abs(f.shap_value) / maxAbs) * 100}%` }}
                      />
                    )}
                  </div>
                  <span className={`w-14 text-right font-mono ${f.shap_value >= 0 ? "text-soc-danger" : "text-soc-primary"}`}>
                    {f.shap_value >= 0 ? "+" : ""}{f.shap_value.toFixed(3)}
                  </span>
                </div>
              ))}
              <p className="mt-2 text-[10px] text-soc-muted">
                Red = fraud-pushing · Blue = fraud-reducing
              </p>
            </>
          ) : (
            <p className="text-[10px] text-soc-muted italic">
              Feature-level attribution unavailable for this event — velocity signals are in-memory only.
            </p>
          )}

          {result.ai_explanation ? (
            <div className="mt-4 rounded-lg border border-soc-border bg-soc-elevated p-4">
              <p className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-soc-muted">
                AI Analysis · Groq
              </p>
              <div className="max-h-80 overflow-y-auto">
                <MarkdownText text={result.ai_explanation} />
              </div>
            </div>
          ) : (
            <div className="mt-4 rounded-lg border border-soc-border bg-soc-elevated p-4">
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-soc-muted">
                AI Analysis
              </p>
              <p className="text-xs text-soc-muted">
                Set <span className="font-mono text-soc-text">GROQ_API_KEY</span> in the gateway env to enable narrative explanations.
              </p>
            </div>
          )}

          {/* Analyst action buttons */}
          <div className="mt-4 flex gap-2 border-t border-soc-border pt-4">
            {blocked ? (
              <span className="flex items-center gap-1.5 rounded-lg bg-soc-danger-light px-3 py-1.5 text-xs font-semibold text-soc-danger">
                ✓ Flagged for review
              </span>
            ) : (
              <button
                type="button"
                onClick={() => setBlocked(true)}
                className="rounded-lg bg-soc-danger px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:opacity-90"
              >
                Block
              </button>
            )}
            {surveillance ? (
              <span className="flex items-center gap-1.5 rounded-lg bg-soc-primary-light px-3 py-1.5 text-xs font-semibold text-soc-primary">
                ✓ Under surveillance
              </span>
            ) : (
              <button
                type="button"
                onClick={() => setSurveillance(true)}
                className="rounded-lg border border-soc-border bg-soc-elevated px-3 py-1.5 text-xs font-semibold text-soc-text transition-colors hover:border-soc-primary hover:text-soc-primary"
              >
                Surveillance
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
