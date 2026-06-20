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
    return <p className="text-sm text-gray-400">No reason codes.</p>;
  }
  return (
    <ul className="space-y-1 text-sm">
      {reasonCodes.map((rc, i) => (
        <li key={`${rc.code}-${i}`} className="flex justify-between gap-2">
          <span className="font-medium">{rc.code}</span>
          <span className="text-gray-500">
            {rc.detail}
            {rc.sigma != null ? ` (σ=${rc.sigma.toFixed(2)})` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}
