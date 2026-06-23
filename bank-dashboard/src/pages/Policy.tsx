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
    return <p className="text-sm text-gray-400">Loading...</p>;
  }

  return (
    <div className="max-w-lg space-y-4">
      <h1 className="text-xl font-semibold">Active policy</h1>
      <p className="text-sm text-gray-500">Scoring mode: {policy.scoring_mode}</p>

      <div className="rounded-lg border bg-white p-3 shadow-sm">
        <h2 className="mb-2 text-sm font-medium text-gray-600">Thresholds</h2>
        {Object.entries(policy.thresholds).map(([key, value]) => (
          <label key={key} className="mb-2 flex items-center justify-between text-sm">
            {key}
            <input
              type="number"
              className="w-24 rounded border px-2 py-1 focus:border-cbi-primary focus:outline-none"
              value={value}
              onChange={(e) => setThreshold(key, Number(e.target.value))}
            />
          </label>
        ))}
      </div>

      <div className="rounded-lg border bg-white p-3 shadow-sm">
        <h2 className="mb-2 text-sm font-medium text-gray-600">Amplifiers</h2>
        {Object.entries(policy.amplifiers).map(([key, value]) => (
          <div key={key} className="flex items-center justify-between text-sm">
            <span>{key}</span>
            <span>×{value}</span>
          </div>
        ))}
      </div>

      <button
        type="button"
        className="rounded bg-cbi-primary px-3 py-2 text-sm text-white hover:bg-cbi-primary-dark"
        onClick={() => void save()}
      >
        Save policy
      </button>
      {saved && <p className="text-sm text-green-600">Saved -- takes effect immediately, no restart.</p>}
    </div>
  );
}
