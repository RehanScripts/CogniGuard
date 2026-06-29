// Identity-verification panel (gateway Phase 20-22): the live Trust Score, per-user
// Behavior Match, and Device Trust for the most recent risk-score event. Fed from the
// SOC WS feed (ws.ts RiskScoreEvent) -- behavior_match_score is null until the entity's
// user is enrolled (cold-start), shown as "calibrating".
// Demo jitter: displayed values breathe ±2-4 pts every 2 s to signal live activity.
import { useEffect, useRef, useState } from "react";

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
  const barColor = !known
    ? "bg-soc-border"
    : v >= 70
      ? "bg-soc-success"
      : v >= 40
        ? "bg-soc-warning"
        : "bg-soc-danger";

  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="text-soc-muted">{label}</span>
        <span className="font-semibold text-soc-text">
          {known ? `${v.toFixed(0)}${suffix}` : "calibrating…"}
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-soc-elevated">
        <div
          className={`h-1.5 rounded-full transition-all duration-700 ${barColor}`}
          style={{ width: `${Math.max(0, Math.min(100, v))}%` }}
        />
      </div>
    </div>
  );
}

function jitter(base: number | null | undefined, delta: number): number | null | undefined {
  if (base == null) return base;
  const offset = (Math.random() * 2 - 1) * delta;
  return Math.max(0, Math.min(100, base + offset));
}

interface DisplayValues {
  trust: number | null | undefined;
  behavior: number | null | undefined;
  device: number | null | undefined;
  risk: number | null | undefined;
}

export default function TrustPanel({ latest }: { latest: RiskScoreEvent | null }) {
  const [display, setDisplay] = useState<DisplayValues>({
    trust: null,
    behavior: null,
    device: null,
    risk: null,
  });
  const latestRef = useRef(latest);
  latestRef.current = latest;

  // Reset display values whenever a real WS event arrives
  useEffect(() => {
    if (!latest) return;
    setDisplay({
      trust: latest.trust_score,
      behavior: latest.behavior_match_score,
      device: latest.device_score,
      risk: latest.final_risk_score,
    });
  }, [latest]);

  // Breathe every 2 s when we have live data
  useEffect(() => {
    if (!latest) return;
    const id = setInterval(() => {
      const l = latestRef.current;
      if (!l) return;
      setDisplay({
        trust: jitter(l.trust_score, 3),
        behavior: jitter(l.behavior_match_score, 2),
        device: jitter(l.device_score, 2),
        risk: jitter(l.final_risk_score, 4),
      });
    }, 2000);
    return () => clearInterval(id);
  }, [latest]);

  if (!latest) {
    return <p className="text-sm text-soc-muted">Awaiting scored events…</p>;
  }
  return (
    <div className="space-y-3">
      <p className="font-mono text-xs text-soc-muted capitalize">
        {latest.entity_type}
        {latest.entity_id ? ` · ${latest.entity_id.slice(0, 8)}` : ""}
      </p>
      <Gauge label="Trust Score" value={display.trust} />
      <Gauge label="Behavior Match" value={display.behavior} suffix="%" />
      <Gauge label="Device Trust" value={display.device} />
      <Gauge label="Risk" value={display.risk} />
    </div>
  );
}
