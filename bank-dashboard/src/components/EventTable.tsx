export interface EventRow {
  key: string;
  entityType: string;
  entityId?: string | null;
  userId?: string | null;
  band?: string | null;
  score?: number | null;
  action?: string | null;
  ts: string;
  scoreId?: string | null;
}

function BandBadge({ band }: { band: string | null | undefined }) {
  if (!band) return <span className="text-soc-muted">—</span>;
  const cls: Record<string, string> = {
    low: "badge-low",
    medium: "badge-medium",
    high: "badge-high",
    very_high: "badge-very_high",
  };
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${cls[band] ?? "bg-soc-bg text-soc-muted"}`}>
      {band.replace("_", " ")}
    </span>
  );
}

function ActionBadge({ action }: { action: string | null | undefined }) {
  if (!action) return <span className="text-soc-muted">—</span>;
  const cls: Record<string, string> = {
    allow: "badge-allow",
    verify: "badge-verify",
    block: "badge-block",
  };
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${cls[action] ?? "bg-soc-bg text-soc-muted"}`}>
      {action}
    </span>
  );
}

interface EventTableProps {
  rows: EventRow[];
  onRowClick?: (row: EventRow) => void;
}

export default function EventTable({ rows, onRowClick }: EventTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-soc-border bg-soc-elevated text-[11px] font-semibold uppercase tracking-wider text-soc-muted">
            <th className="px-4 py-3 text-left">Entity</th>
            <th className="px-4 py-3 text-left">Risk Band</th>
            <th className="px-4 py-3 text-right">Score</th>
            <th className="px-4 py-3 text-left">Action</th>
            <th className="px-4 py-3 text-right">Time</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-soc-border">
          {rows.length === 0 && (
            <tr>
              <td colSpan={5} className="px-4 py-10 text-center text-sm text-soc-muted">
                No events yet — waiting for live traffic…
              </td>
            </tr>
          )}
          {rows.map((row, i) => (
            <tr
              key={row.key}
              className={`cursor-pointer transition-colors hover:bg-soc-primary-light/30 ${i % 2 === 0 ? "" : "bg-soc-elevated/50"}`}
              onClick={() => onRowClick?.(row)}
              title="Click to AI investigate"
            >
              <td className="px-4 py-3">
                <span className="font-medium text-soc-text capitalize">{row.entityType}</span>
                {row.entityId && (
                  <span className="ml-1.5 font-mono text-[11px] text-soc-muted">
                    {row.entityId.slice(0, 8)}…
                  </span>
                )}
                {row.userId && (
                  <p className="mt-0.5 font-mono text-[10px] text-soc-muted">{row.userId.slice(0, 12)}…</p>
                )}
              </td>
              <td className="px-4 py-3">
                <BandBadge band={row.band} />
              </td>
              <td className="px-4 py-3 text-right font-mono text-sm font-semibold text-soc-text">
                {row.score != null ? row.score.toFixed(1) : "—"}
              </td>
              <td className="px-4 py-3">
                <ActionBadge action={row.action} />
              </td>
              <td className="px-4 py-3 text-right font-mono text-[11px] text-soc-muted">
                {new Date(row.ts).toLocaleTimeString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
