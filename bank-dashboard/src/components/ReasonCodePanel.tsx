export interface ReasonCodeLike {
  code: string;
  detail?: string | null;
  sigma?: number | null;
}

interface ReasonCodePanelProps {
  reasonCodes: ReasonCodeLike[];
}

export default function ReasonCodePanel({ reasonCodes }: ReasonCodePanelProps) {
  if (reasonCodes.length === 0) {
    return <p className="text-sm text-soc-muted">No reason codes.</p>;
  }
  return (
    <ul className="space-y-1.5 text-xs">
      {reasonCodes.map((rc, i) => (
        <li key={`${rc.code}-${i}`} className="flex items-start justify-between gap-3 rounded-lg bg-soc-elevated px-3 py-2">
          <span className="font-mono font-bold text-soc-text">{rc.code}</span>
          <span className="text-right text-soc-muted">
            {rc.detail}
            {rc.sigma != null ? ` (σ=${rc.sigma.toFixed(2)})` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}
