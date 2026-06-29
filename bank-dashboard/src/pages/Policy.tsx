import { useEffect, useState } from "react";

import { type PolicyDict, getPolicy, putPolicy } from "../api";

export default function Policy() {
  const [policy, setPolicy] = useState<PolicyDict | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    getPolicy()
      .then(({ body }) => setPolicy(body.active_policy))
      .catch(() => undefined);
  }, []);

  function setThreshold(key: string, value: number) {
    setPolicy((prev) => (prev ? { ...prev, thresholds: { ...prev.thresholds, [key]: value } } : prev));
    setSaved(false);
  }

  async function save() {
    if (!policy) return;
    const { body } = await putPolicy(policy);
    setPolicy(body.active_policy);
    setSaved(true);
  }

  if (!policy) {
    return (
      <div className="flex items-center gap-2 text-sm text-soc-muted">
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-soc-primary border-t-transparent" />
        Loading policy…
      </div>
    );
  }

  return (
    <div className="max-w-lg space-y-5">
      {/* Header */}
      <div>
        <h1 className="font-headline text-2xl font-bold text-soc-text">Active Policy</h1>
        <p className="mt-0.5 text-sm text-soc-muted">
          Scoring mode: <span className="font-medium text-soc-primary">{policy.scoring_mode}</span>
        </p>
      </div>

      {/* Thresholds */}
      <div className="card overflow-hidden">
        <div className="card-header">
          <h2 className="font-semibold text-soc-text">Risk Thresholds</h2>
        </div>
        <div className="space-y-3 p-5">
          {Object.entries(policy.thresholds).map(([key, value]) => (
            <label key={key} className="flex items-center justify-between gap-4 text-sm">
              <span className="font-medium capitalize text-soc-text">{key.replace(/_/g, " ")}</span>
              <input
                type="number"
                className="w-24 rounded-lg border border-soc-border bg-soc-bg px-3 py-1.5 text-right text-sm text-soc-text outline-none focus:border-soc-primary"
                value={value}
                onChange={(e) => setThreshold(key, Number(e.target.value))}
              />
            </label>
          ))}
        </div>
      </div>

      {/* Amplifiers */}
      <div className="card overflow-hidden">
        <div className="card-header flex items-center justify-between">
          <h2 className="font-semibold text-soc-text">Risk Amplifiers</h2>
          <span className="text-xs text-soc-muted">multiplicative overrides</span>
        </div>
        <div className="space-y-2 p-5">
          {Object.entries(policy.amplifiers).map(([key, value]) => (
            <div key={key} className="flex items-center justify-between rounded-lg bg-soc-elevated px-3 py-2 text-sm">
              <span className="capitalize text-soc-text">{key.replace(/_/g, " ")}</span>
              <span className="font-mono font-bold text-soc-primary">×{value}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-4">
        <button
          type="button"
          className="rounded-lg bg-soc-primary px-5 py-2.5 text-sm font-bold text-white transition-all hover:bg-cbi-primary-dark active:scale-[0.98]"
          onClick={() => void save()}
        >
          Save Policy
        </button>
        {saved && (
          <p className="text-sm font-medium text-soc-success">
            ✓ Saved — takes effect immediately
          </p>
        )}
      </div>
    </div>
  );
}
