import { useEffect, useState } from "react";

import { type EventOut, listEvents } from "../api";
import AlertPanel from "../components/AlertPanel";
import BandDistribution from "../components/BandDistribution";
import EventTable, { type EventRow } from "../components/EventTable";
import TrustPanel from "../components/TrustPanel";
import {
  type RiskScoreEvent,
  type SocFeedEvent,
  connectSocFeed,
  isDecisionEvent,
  isRiskScoreEvent,
} from "../ws";

function eventOutToRow(e: EventOut): EventRow {
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

function socEventToRow(event: SocFeedEvent, key: string): EventRow {
  if (isDecisionEvent(event)) {
    return {
      key,
      entityType: event.entity_type,
      entityId: event.entity_id,
      userId: event.user_id,
      band: null,
      score: null,
      action: event.action,
      ts: event.ts,
    };
  }
  return {
    key,
    entityType: event.entity_type,
    entityId: event.entity_id,
    userId: event.user_id,
    band: event.risk_band,
    score: event.final_risk_score,
    action: null,
    ts: event.ts,
  };
}

const MAX_ROWS = 200;

export default function Live() {
  const [rows, setRows] = useState<EventRow[]>([]);
  const [latestRisk, setLatestRisk] = useState<RiskScoreEvent | null>(null);
  const [wsStatus, setWsStatus] = useState<"connecting" | "open" | "closed">("connecting");

  useEffect(() => {
    // The broadcaster only tails "latest" (no Kafka backlog replay) -- backfill from
    // the REST history so the page isn't empty until new live traffic arrives.
    listEvents({ limit: 50 })
      .then(({ body }) => setRows(body.map(eventOutToRow)))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    let counter = 0;
    const disconnect = connectSocFeed((event) => {
      counter += 1;
      setRows((prev) => [socEventToRow(event, `live-${counter}`), ...prev].slice(0, MAX_ROWS));
      if (isRiskScoreEvent(event)) {
        setLatestRisk(event);
      }
    }, setWsStatus);
    return disconnect;
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Live feed</h1>
        <span className="text-sm text-gray-500">WS: {wsStatus}</span>
      </div>
      <div className="grid grid-cols-3 gap-4">
        <div className="col-span-2 rounded-lg border bg-white p-3 shadow-sm">
          <EventTable rows={rows} />
        </div>
        <div className="space-y-4">
          <div className="rounded-lg border bg-white p-3 shadow-sm">
            <h2 className="mb-2 text-sm font-medium text-gray-600">Identity & Trust</h2>
            <TrustPanel latest={latestRisk} />
          </div>
          <div className="rounded-lg border bg-white p-3 shadow-sm">
            <h2 className="mb-2 text-sm font-medium text-gray-600">Band distribution</h2>
            <BandDistribution rows={rows} />
          </div>
          <div className="rounded-lg border bg-white p-3 shadow-sm">
            <h2 className="mb-2 text-sm font-medium text-gray-600">Alerts</h2>
            <AlertPanel rows={rows} />
          </div>
        </div>
      </div>
    </div>
  );
}
