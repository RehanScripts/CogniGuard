import type { RiskBand } from "../api";

const BAND_STYLES: Record<RiskBand, string> = {
  low: "bg-green-100 text-green-800 border-green-300",
  medium: "bg-yellow-100 text-yellow-800 border-yellow-300",
  high: "bg-orange-100 text-orange-800 border-orange-300",
  very_high: "bg-red-100 text-red-800 border-red-300",
};

interface RiskBadgeProps {
  band: RiskBand;
  score: number;
}

export default function RiskBadge({ band, score }: RiskBadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-3 py-1 text-sm font-medium ${BAND_STYLES[band]}`}
    >
      {band.replace("_", " ")} · {score.toFixed(0)}
    </span>
  );
}
