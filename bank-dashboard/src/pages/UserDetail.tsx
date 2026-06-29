import { Fragment, useState, useEffect } from "react";
import { useParams } from "react-router-dom";

import { type UserDetailOut, getUserDetail } from "../api";
import AuthTimeline from "../components/AuthTimeline";
import DeviceIntelligence from "../components/DeviceIntelligence";
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
  const [activeTab, setActiveTab] = useState<"events" | "timeline" | "devices">("events");

  useEffect(() => {
    if (!userId) return;
    getUserDetail(userId)
      .then(({ body }) => setDetail(body))
      .catch(() => undefined);
  }, [userId]);

  if (!detail) {
    return (
      <div className="flex items-center gap-2 text-sm text-soc-muted">
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-soc-primary border-t-transparent" />
        Loading user…
      </div>
    );
  }

  const tabs = [
    { key: "events" as const, label: "Recent Events" },
    { key: "timeline" as const, label: "Auth Timeline" },
    { key: "devices" as const, label: "Devices" },
  ];

  const u = detail.user as Record<string, unknown>;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <h1 className="font-headline text-2xl font-bold text-soc-text">User Profile</h1>
        <p className="font-mono mt-0.5 text-xs text-soc-muted">{userId}</p>
      </div>

      {/* Profile card */}
      <div className="card overflow-hidden">
        <div className="card-header">
          <h2 className="font-semibold text-soc-text">Account Info</h2>
        </div>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 p-5 text-sm md:grid-cols-3">
          {Object.entries(u).map(([key, val]) => (
            <Fragment key={key}>
              <dt className="text-xs font-semibold uppercase tracking-wider text-soc-muted">
                {key.replace(/_/g, " ")}
              </dt>
              <dd className="font-mono text-xs text-soc-text break-all">
                {val == null ? "—" : String(val)}
              </dd>
            </Fragment>
          ))}
        </dl>
      </div>

      <QuarantineStatus quarantinedSamples={detail.quarantined_samples} />

      {/* Tabs */}
      <div className="flex gap-1 border-b border-soc-border">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setActiveTab(t.key)}
            className={`mb-[-1px] px-4 pb-2.5 text-sm font-semibold border-b-2 transition-colors ${
              activeTab === t.key
                ? "border-soc-primary text-soc-primary"
                : "border-transparent text-soc-muted hover:text-soc-text"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {activeTab === "events" && (
        <EventTable rows={detail.recent_events.map(toRow)} />
      )}

      {activeTab === "timeline" && userId && (
        <div className="card overflow-hidden">
          <div className="card-header">
            <h2 className="font-semibold text-soc-text">Authentication Timeline</h2>
          </div>
          <div className="p-5">
            <AuthTimeline userId={userId} />
          </div>
        </div>
      )}

      {activeTab === "devices" && (
        <div className="space-y-4">
          {detail.devices.length === 0 ? (
            <div className="card px-5 py-10 text-center text-sm text-soc-muted">
              No devices linked to this account.
            </div>
          ) : (
            detail.devices.map((d) => (
              <div key={String(d.device_id)} className="card overflow-hidden">
                <div className="card-header flex items-center gap-2">
                  <p className="font-mono text-xs font-semibold text-soc-text">
                    Device {String(d.device_id).slice(0, 12)}…
                  </p>
                  {d.is_trusted ? (
                    <span className="rounded-full bg-band-low-bg px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-band-low">
                      trusted
                    </span>
                  ) : (
                    <span className="rounded-full bg-soc-elevated px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-soc-muted">
                      not trusted
                    </span>
                  )}
                </div>
                <div className="p-4">
                  <DeviceIntelligence deviceId={String(d.device_id)} />
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
