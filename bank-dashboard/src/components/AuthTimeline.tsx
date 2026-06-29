import { useEffect, useState } from "react";

import { type AuthTimelineEventOut, getAuthTimeline } from "../api";

interface Props {
  userId: string;
}

const DECISION_STYLES: Record<string, string> = {
  allow: "bg-band-low-bg text-band-low",
  verify: "bg-band-medium-bg text-band-medium",
  block: "bg-band-high-bg text-band-high",
};

const EVENT_ICONS: Record<string, string> = {
  success: "✓",
  step_up: "🔐",
  failure: "✗",
  attempt: "·",
};

export default function AuthTimeline({ userId }: Props) {
  const [events, setEvents] = useState<AuthTimelineEventOut[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getAuthTimeline(userId)
      .then(({ body }) => setEvents(body))
      .catch(() => undefined)
      .finally(() => setLoading(false));
  }, [userId]);

  if (loading) return <p className="text-xs text-soc-muted">Loading timeline…</p>;
  if (!events.length) return <p className="text-xs text-soc-muted">No auth events.</p>;

  return (
    <div className="relative space-y-2 pl-4">
      <div className="absolute bottom-0 left-1.5 top-0 w-px bg-soc-border" />
      {events.map((ev) => (
        <div key={ev.event_id} className="relative flex gap-3">
          <div className="absolute -left-1 flex h-5 w-5 items-center justify-center rounded-full border border-soc-border bg-soc-surface text-[10px] shadow-sm">
            {EVENT_ICONS[ev.event_type ?? ""] ?? "·"}
          </div>
          <div className="ml-5 flex-1 rounded-xl border border-soc-border bg-soc-elevated p-2.5 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold capitalize text-soc-text">{(ev.event_type ?? "event").replace("_", " ")}</span>
              {ev.decision && (
                <span className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${DECISION_STYLES[ev.decision] ?? "bg-soc-elevated text-soc-muted"}`}>
                  {ev.decision}
                </span>
              )}
            </div>
            {ev.challenge_type && (
              <p className="mt-1 text-soc-muted">Factor: <span className="font-medium text-soc-text">{ev.challenge_type}</span></p>
            )}
            {ev.device_label && (
              <p className="mt-0.5 text-soc-muted">{ev.device_label}</p>
            )}
            {ev.created_at && (
              <p className="mt-1 font-mono text-[10px] text-soc-muted">{new Date(ev.created_at).toLocaleString("en-IN")}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
