import { describe, expect, it } from "vitest";

import { type SocFeedEvent, isDecisionEvent, isRiskScoreEvent } from "./ws";

const decisionEvent: SocFeedEvent = {
  entity_type: "login",
  entity_id: "abc",
  action: "verify",
  required_factors: ["OTP"],
  reason_codes: [],
  ts: "2026-06-20T05:00:00Z",
};

const riskScoreEvent: SocFeedEvent = {
  entity_type: "login",
  entity_id: "abc",
  behavior_score: 0.1,
  device_score: 0.0,
  transaction_score: 0.0,
  final_risk_score: 10,
  risk_band: "low",
  model_version: "xgboost_txn@2026-06-17",
  ts: "2026-06-20T05:00:00Z",
};

describe("soc feed event classification", () => {
  it("classifies a message with `action` as a DecisionEvent", () => {
    expect(isDecisionEvent(decisionEvent)).toBe(true);
    expect(isRiskScoreEvent(decisionEvent)).toBe(false);
  });

  it("classifies a message with `final_risk_score` as a RiskScoreEvent", () => {
    expect(isRiskScoreEvent(riskScoreEvent)).toBe(true);
    expect(isDecisionEvent(riskScoreEvent)).toBe(false);
  });
});
