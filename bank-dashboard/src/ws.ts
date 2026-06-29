// WebSocket client for /ws/soc-feed (gateway/app/routers/ws.py). Field names mirror
// gateway/app/schemas/topics.py exactly.
import type { RiskBand } from "./api";

export interface RiskScoreEvent {
  entity_type: "login" | "transaction";
  entity_id: string;
  user_id?: string | null;
  score_id?: string | null;
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

// Emitted by case_mgmt.maybe_open_case after db.commit() — guaranteed in DB before arrival.
export interface CaseOpenedEvent {
  event_type: "case_opened";
  case_id: string;
  user_id?: string | null;
  transaction_id?: string | null;
  alert_type?: string | null;
  severity?: string | null;
  status: string;
  risk_band?: string | null;
  action?: string | null;
  reason_codes?: { code: string; detail?: string }[] | null;
  created_at?: string | null;
}

export type SocFeedEvent = RiskScoreEvent | DecisionEvent | CaseOpenedEvent;

// Discriminators — CaseOpenedEvent has an explicit `event_type` field; the two Kafka
// events are told apart by field presence (no wire discriminator on those).
export function isCaseOpenedEvent(e: SocFeedEvent): e is CaseOpenedEvent {
  return "event_type" in e && (e as CaseOpenedEvent).event_type === "case_opened";
}

export function isDecisionEvent(event: SocFeedEvent): event is DecisionEvent {
  return !isCaseOpenedEvent(event) && "action" in event;
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
