import { AlertTriangle, ShieldOff } from "lucide-react";

import type { EventRow } from "./EventTable";

export default function AlertPanel({ rows }: { rows: EventRow[] }) {
  const alerts = rows.filter((r) => r.band === "very_high" || r.action === "block").slice(0, 10);

  if (alerts.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-4 text-soc-muted">
        <ShieldOff className="h-5 w-5 opacity-40" />
        <p className="text-xs">No critical alerts</p>
      </div>
    );
  }

  return (
    <ul className="space-y-2">
      {alerts.map((row) => (
        <li key={row.key} className="flex items-start gap-2 rounded-lg border border-soc-danger-light bg-soc-danger-light p-2.5">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-soc-danger" />
          <div className="min-w-0">
            <p className="text-xs font-semibold capitalize text-soc-danger">
              {row.entityType}{row.action === "block" ? " — Blocked" : " — Critical Risk"}
            </p>
            {row.entityId && (
              <p className="mt-0.5 font-mono text-[10px] text-soc-muted">{row.entityId.slice(0, 16)}…</p>
            )}
            <p className="mt-0.5 text-[10px] text-soc-muted">{new Date(row.ts).toLocaleTimeString()}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}
