import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { type UserDetailOut, getUserDetail } from "../api";
import EventTable, { type EventRow } from "../components/EventTable";
import QuarantineStatus from "../components/QuarantineStatus";

function toRow(e: UserDetailOut["recent_events"][number]): EventRow {
  return {
    key: e.score_id,
    entityType: e.entity_type,
    entityId: e.entity_id,
    userId: e.user_id,
    band: e.risk_band,
    score: e.final_risk_score,
    action: e.action,
    ts: e.scored_at ?? new Date().toISOString(),
  };
}

export default function UserDetail() {
  const { userId } = useParams<{ userId: string }>();
  const [detail, setDetail] = useState<UserDetailOut | null>(null);

  useEffect(() => {
    if (!userId) return;
    getUserDetail(userId)
      .then(({ body }) => setDetail(body))
      .catch(() => undefined);
  }, [userId]);

  if (!detail) {
    return <p className="text-sm text-gray-400">Loading...</p>;
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">User {userId?.slice(0, 8)}</h1>
      <pre className="rounded border bg-gray-50 p-3 text-xs">{JSON.stringify(detail.user, null, 2)}</pre>
      <QuarantineStatus quarantinedSamples={detail.quarantined_samples} />
      <div>
        <h2 className="mb-2 text-sm font-medium text-gray-600">Recent events</h2>
        <EventTable rows={detail.recent_events.map(toRow)} />
      </div>
    </div>
  );
}
