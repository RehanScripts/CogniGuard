// Identity-verification panel (gateway Phase 20-22): the live Trust Score, per-user
// Behavior Match, and Device Trust for the most recent risk-score event. Fed from the
// SOC WS feed (ws.ts RiskScoreEvent) -- behavior_match_score is null until the entity's
// user is enrolled (cold-start), shown as "calibrating".
import type { RiskScoreEvent } from "../ws";

function Gauge({
  label,
  value,
  suffix = "/100",
}: {
  label: string;
  value: number | null | undefined;
  suffix?: string;
}) {
  const known = value !== null && value !== undefined;
  const v = known ? value : 0;
  const tone = !known
    ? "bg-gray-300"
    : v >= 70
      ? "bg-green-500"
      : v >= 40
        ? "bg-amber-500"
        : "bg-red-500";
  return (
    <div>
      <div className="flex items-center justify-between text-xs text-gray-600">
        <span>{label}</span>
        <span className="font-medium">{known ? `${v.toFixed(0)}${suffix}` : "calibrating…"}</span>
      </div>
      <div className="mt-1 h-2 w-full overflow-hidden rounded bg-gray-100">
        <div className={`h-2 rounded ${tone}`} style={{ width: `${Math.max(0, Math.min(100, v))}%` }} />
      </div>
    </div>
  );
}

export default function TrustPanel({ latest }: { latest: RiskScoreEvent | null }) {
  if (!latest) {
    return <p className="text-sm text-gray-400">Awaiting scored events…</p>;
  }
  return (
    <div className="space-y-3">
      <div className="text-xs text-gray-500">
        {latest.entity_type}
        {latest.entity_id ? ` · ${latest.entity_id.slice(0, 8)}` : ""}
      </div>
      <Gauge label="Trust Score" value={latest.trust_score} />
      <Gauge label="Behavior Match" value={latest.behavior_match_score} suffix="%" />
      <Gauge label="Device Trust" value={latest.device_score} />
      <Gauge label="Risk" value={latest.final_risk_score} />
    </div>
  );
}
