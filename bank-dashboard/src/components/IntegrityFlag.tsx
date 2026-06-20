interface IntegrityFlagProps {
  integrity?: "OK" | "INTEGRITY_REJECT" | null;
}

// Built to consume an `integrity` field on a decision event, but note: today an
// INTEGRITY_REJECT never reaches Kafka -- auth_flow.login / payment_flow.score_payment
// return their reject body directly without calling emit_risk_score/emit_decision,
// and neither RiskScoreEvent nor DecisionEvent (gateway/app/schemas/topics.py) carries
// an `integrity` field regardless. So this will never actually render from the live
// /ws/soc-feed under the current Phase 7-9 contracts -- flagged as a cross-phase gap,
// not fixed here.
export default function IntegrityFlag({ integrity }: IntegrityFlagProps) {
  if (integrity !== "INTEGRITY_REJECT") return null;
  return (
    <span className="rounded-full bg-red-600 px-2 py-0.5 text-xs font-semibold text-white">
      INTEGRITY_REJECT
    </span>
  );
}
