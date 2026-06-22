// Surfaces the identity-gated Trust Score + per-user behavior-match (gateway Phase 20-22).
// behavior_match_score is null until the user is enrolled (cold-start) -- shown as
// "calibrating" rather than a number.
export default function TrustBadge({
  trustScore,
  behaviorMatch,
}: {
  trustScore?: number | null;
  behaviorMatch?: number | null;
}) {
  if (trustScore == null) return null;

  const tone =
    trustScore >= 70
      ? "border-green-300 bg-green-50 text-green-800"
      : trustScore >= 40
        ? "border-amber-300 bg-amber-50 text-amber-800"
        : "border-red-300 bg-red-50 text-red-800";

  return (
    <div className={`mt-4 rounded border p-3 text-sm ${tone}`}>
      <div className="flex items-center justify-between">
        <span>Identity Trust Score</span>
        <span className="font-semibold">{trustScore.toFixed(0)}/100</span>
      </div>
      <div className="mt-1 flex items-center justify-between text-xs opacity-80">
        <span>Behavior match to your profile</span>
        <span>{behaviorMatch == null ? "calibrating…" : `${behaviorMatch.toFixed(0)}%`}</span>
      </div>
    </div>
  );
}
