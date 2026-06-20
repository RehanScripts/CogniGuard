import type { EventRow } from "./EventTable";

interface AlertPanelProps {
  rows: EventRow[];
}

export default function AlertPanel({ rows }: AlertPanelProps) {
  const alerts = rows.filter((r) => r.band === "very_high" || r.action === "block");
  if (alerts.length === 0) {
    return <p className="text-sm text-gray-400">No active alerts.</p>;
  }
  return (
    <ul className="space-y-1">
      {alerts.map((row) => (
        <li key={row.key} className="rounded bg-red-50 px-2 py-1 text-sm text-red-800">
          {row.entityType} {row.entityId?.slice(0, 8)} -- {row.band ?? row.action}
        </li>
      ))}
    </ul>
  );
}
