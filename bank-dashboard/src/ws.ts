// WebSocket client for /ws/soc-feed (gateway/app/routers/ws.py). Field names mirror
// gateway/app/schemas/topics.py exactly.
import type { RiskBand } from "./api";

export interface RiskScoreEvent {
  entity_type: "login" | "transaction";
  entity_id: string;
  user_id?: string | null;
  behavior_score: number;
  device_score: number;
  transaction_score: number;
  final_risk_score: number;
  risk_band: RiskBand;
  model_version: string;
  ts: string;
  // Continuous identity verification (gateway Phase 20-22). null until enrolled.
  trust_score?: number | null;
  behavior_match_score?: number | null;
}

export interface ReasonCodeLite {
  code: string;
  detail?: string;
  sigma?: number | null;
}

export interface DecisionEvent {
  entity_type: "login" | "transaction";
  entity_id: string;
  user_id?: string | null;
  action: "allow" | "verify" | "block";
  required_factors: string[];
  reason_codes: ReasonCodeLite[];
  ts: string;
}

export type SocFeedEvent = RiskScoreEvent | DecisionEvent;

// No `type` discriminator exists on the wire (confirmed against
// gateway/app/schemas/topics.py, routers/ws.py, services/broadcaster.py) -- this is
// the only way to tell the two apart: DecisionEvent carries `action`, RiskScoreEvent
// carries `final_risk_score`. Inferred, not contractual -- would break if both
// schemas ever grow an overlapping field with one of these names.
export function isDecisionEvent(event: SocFeedEvent): event is DecisionEvent {
  return "action" in event;
}

export function isRiskScoreEvent(event: SocFeedEvent): event is RiskScoreEvent {
  return "final_risk_score" in event;
}

export function connectSocFeed(
  onEvent: (event: SocFeedEvent) => void,
  onStatusChange?: (status: "open" | "closed") => void,
): () => void {
  const wsBase = import.meta.env.VITE_WS_BASE || "ws://localhost:8000";
  const socket = new WebSocket(`${wsBase}/ws/soc-feed`);

  socket.onopen = () => onStatusChange?.("open");
  socket.onclose = () => onStatusChange?.("closed");
  socket.onmessage = (event: MessageEvent<string>) => {
    try {
      const parsed = JSON.parse(event.data) as SocFeedEvent;
      onEvent(parsed);
    } catch {
      // ignore malformed frames
    }
  };

  return () => socket.close();
}
