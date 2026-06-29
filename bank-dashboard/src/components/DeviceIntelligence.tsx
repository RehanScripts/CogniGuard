import { Fragment, useEffect, useState } from "react";

import { type DeviceIntelOut, getDeviceIntel } from "../api";

interface Props {
  deviceId: string;
}

const TRUST_CLASS_STYLES: Record<string, string> = {
  trusted: "bg-band-low-bg text-band-low",
  known: "bg-soc-primary-light text-soc-primary",
  new: "bg-band-medium-bg text-band-medium",
  suspicious: "bg-band-high-bg text-band-high",
};

export default function DeviceIntelligence({ deviceId }: Props) {
  const [intel, setIntel] = useState<DeviceIntelOut | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getDeviceIntel(deviceId)
      .then(({ body }) => setIntel(body))
      .catch(() => undefined)
      .finally(() => setLoading(false));
  }, [deviceId]);

  if (loading) return <p className="text-xs text-soc-muted">Loading device intel…</p>;
  if (!intel) return <p className="text-xs text-soc-muted">Device not found.</p>;

  const trustStyle = TRUST_CLASS_STYLES[intel.trust_class ?? ""] ?? "bg-soc-elevated text-soc-muted";

  return (
    <div className="rounded-xl border border-soc-border bg-soc-elevated p-3 text-xs space-y-3">
      <div className="flex items-center justify-between">
        <span className="font-semibold text-soc-text">
          {intel.os ?? "Unknown OS"} · {intel.browser ?? "Unknown browser"}
        </span>
        {intel.trust_class && (
          <span className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${trustStyle}`}>
            {intel.trust_class}
          </span>
        )}
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5">
        {[
          ["Trust score", intel.trust_score != null ? intel.trust_score.toFixed(0) : "—", false],
          ["Rooted", intel.is_rooted ? "Yes" : "No", intel.is_rooted],
          ["Emulator", intel.is_emulator ? "Yes" : "No", intel.is_emulator],
          ["Linked users", String(intel.linked_user_count), false],
          ["Scored events", String(intel.event_count), false],
        ].map(([label, value, isAlert]) => (
          <Fragment key={String(label)}>
            <dt className="text-soc-muted">{label}</dt>
            <dd className={`font-medium ${isAlert ? "text-soc-danger" : "text-soc-text"}`}>{value}</dd>
          </Fragment>
        ))}
      </dl>

      {intel.geo_trend.length > 0 && (
        <div>
          <p className="mb-1 font-semibold text-soc-muted">Recent locations</p>
          <div className="space-y-0.5">
            {intel.geo_trend.map((g, i) => (
              <p key={i} className="text-soc-muted">
                {[g.city, g.country].filter(Boolean).join(", ") || g.ip_address || "Unknown"}
                {g.seen_at && ` · ${new Date(g.seen_at).toLocaleDateString("en-IN")}`}
              </p>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
