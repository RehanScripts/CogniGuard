import { Activity, AlertTriangle, BarChart2, CheckCircle, Radio, Users } from "lucide-react";
import { useEffect, useState } from "react";

import { type EventOut, listEvents } from "../api";
import AlertPanel from "../components/AlertPanel";
import BandDistribution from "../components/BandDistribution";
import EventDrawer from "../components/EventDrawer";
import EventTable, { type EventRow } from "../components/EventTable";
import TrustPanel from "../components/TrustPanel";
import {
  type RiskScoreEvent,
  type SocFeedEvent,
  connectSocFeed,
  isCaseOpenedEvent,
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
    scoreId: e.score_id,
  };
}

function socEventToRow(event: SocFeedEvent, key: string): EventRow | null {
  if (isCaseOpenedEvent(event)) return null;
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
      scoreId: null,
    };
  }
  const rse = event as RiskScoreEvent;
  return {
    key,
    entityType: rse.entity_type,
    entityId: rse.entity_id,
    userId: rse.user_id,
    band: rse.risk_band,
    score: rse.final_risk_score,
    action: null,
    ts: rse.ts,
    scoreId: rse.score_id ?? null,
  };
}

const MAX_ROWS = 200;

export default function Live() {
  const [rows, setRows] = useState<EventRow[]>([]);
  const [latestRisk, setLatestRisk] = useState<RiskScoreEvent | null>(null);
  const [wsStatus, setWsStatus] = useState<"connecting" | "open" | "closed">("connecting");
  const [selectedRow, setSelectedRow] = useState<EventRow | null>(null);

  useEffect(() => {
    listEvents({ limit: 50 })
      .then(({ body }) => setRows(body.map(eventOutToRow)))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    let counter = 0;
    const disconnect = connectSocFeed((event) => {
      counter += 1;
      const row = socEventToRow(event, `live-${counter}`);
      if (row) setRows((prev) => [row, ...prev].slice(0, MAX_ROWS));
      if (isRiskScoreEvent(event)) {
        setLatestRisk(event);
      }
    }, setWsStatus);
    return disconnect;
  }, []);

  const blockCount = rows.filter((r) => r.action === "block").length;
  const highCount = rows.filter((r) => r.band === "high" || r.band === "very_high").length;
  const uniqueUsers = new Set(rows.map((r) => r.userId).filter(Boolean)).size;

  const wsStatusConfig = {
    open: { label: "Live", color: "bg-band-low text-white", dot: "bg-band-low" },
    connecting: { label: "Connecting", color: "bg-soc-warning text-white", dot: "bg-soc-warning" },
    closed: { label: "Disconnected", color: "bg-soc-danger text-white", dot: "bg-soc-danger" },
  }[wsStatus];

  return (
    <div className="space-y-5">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-headline text-2xl font-bold text-soc-text">Live Risk Feed</h1>
          <p className="mt-0.5 text-sm text-soc-muted">Real-time event stream and risk scoring</p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold ${wsStatusConfig.color}`}>
            <span className={`h-1.5 w-1.5 rounded-full bg-white/80 ${wsStatus === "open" ? "animate-pulse" : ""}`} />
            {wsStatusConfig.label}
          </span>
          <span className="text-xs text-soc-muted">{rows.length} events</span>
        </div>
      </div>

      {/* Summary stat cards */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {[
          { icon: Radio, label: "Total Events", value: rows.length, color: "text-soc-primary", bg: "bg-soc-primary-light" },
          { icon: AlertTriangle, label: "Blocks", value: blockCount, color: "text-soc-danger", bg: "bg-soc-danger-light" },
          { icon: Activity, label: "High/Critical Risk", value: highCount, color: "text-soc-warning", bg: "bg-soc-warning-light" },
          { icon: Users, label: "Unique Users", value: uniqueUsers, color: "text-soc-success", bg: "bg-soc-success-light" },
        ].map(({ icon: Icon, label, value, color, bg }) => (
          <div key={label} className="card flex items-center gap-4 p-4">
            <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${bg}`}>
              <Icon className={`h-5 w-5 ${color}`} />
            </div>
            <div>
              <p className="text-xl font-bold text-soc-text">{value}</p>
              <p className="text-xs text-soc-muted">{label}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Main content: event table + side panels */}
      <div className="grid gap-4 xl:grid-cols-4">
        {/* Event table — takes 3 cols */}
        <div className="card xl:col-span-3">
          <div className="card-header flex items-center gap-2">
            <Activity className="h-4 w-4 text-soc-primary" />
            <h2 className="text-sm font-semibold text-soc-text">Risk Events</h2>
            <span className="ml-auto text-[10px] text-soc-muted">Click any row to AI investigate</span>
          </div>
          <EventTable rows={rows} onRowClick={setSelectedRow} />
        </div>

        {/* Side panels */}
        <div className="flex flex-col gap-4">
          <div className="card">
            <div className="card-header flex items-center gap-2">
              <BarChart2 className="h-4 w-4 text-soc-primary" />
              <h2 className="text-sm font-semibold text-soc-text">Risk Distribution</h2>
            </div>
            <div className="p-4">
              <BandDistribution rows={rows} />
            </div>
          </div>

          <div className="card">
            <div className="card-header flex items-center gap-2">
              <CheckCircle className="h-4 w-4 text-soc-primary" />
              <h2 className="text-sm font-semibold text-soc-text">Identity & Trust</h2>
            </div>
            <div className="p-4">
              <TrustPanel latest={latestRisk} />
            </div>
          </div>

          <div className="card">
            <div className="card-header flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-soc-accent" />
              <h2 className="text-sm font-semibold text-soc-text">Alerts</h2>
            </div>
            <div className="p-4">
              <AlertPanel rows={rows} />
            </div>
          </div>
        </div>
      </div>

      {/* Event detail drawer */}
      {selectedRow && (
        <EventDrawer row={selectedRow} onClose={() => setSelectedRow(null)} />
      )}
    </div>
  );
}
