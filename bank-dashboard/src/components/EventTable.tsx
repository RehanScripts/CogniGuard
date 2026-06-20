// Unified row shape so this table can render both the WS live feed (RiskScoreEvent |
// DecisionEvent, no DB id) and the REST admin/events backfill (EventOut) -- callers
// convert to this shape rather than EventTable knowing about both wire formats.
export interface EventRow {
  key: string;
  entityType: string;
  entityId?: string | null;
  band?: string | null;
  score?: number | null;
  action?: string | null;
  ts: string;
}

interface EventTableProps {
  rows: EventRow[];
}

export default function EventTable({ rows }: EventTableProps) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-gray-500">
          <th className="py-1">Entity</th>
          <th>Band</th>
          <th>Score</th>
          <th>Action</th>
          <th>When</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.key} className="border-t">
            <td className="py-1">
              {row.entityType}
              {row.entityId ? ` · ${row.entityId.slice(0, 8)}` : ""}
            </td>
            <td>{row.band ?? "--"}</td>
            <td>{row.score !== null && row.score !== undefined ? row.score.toFixed(0) : "--"}</td>
            <td>{row.action ?? "--"}</td>
            <td>{new Date(row.ts).toLocaleTimeString()}</td>
          </tr>
        ))}
        {rows.length === 0 && (
          <tr>
            <td colSpan={5} className="py-4 text-center text-gray-400">
              No events yet
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
