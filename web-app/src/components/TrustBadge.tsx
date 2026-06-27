import { ShieldAlert } from "lucide-react";

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
    trustScore > 80
      ? "text-emerald-400 bg-emerald-950/40 border-emerald-900"
      : trustScore > 40
        ? "text-amber-400 bg-amber-950/40 border-amber-900"
        : "text-rose-400 bg-rose-950/40 border-rose-900";

  const matchTone =
    behaviorMatch != null && behaviorMatch > 80
      ? "text-emerald-400 bg-emerald-950/40 border-emerald-900"
      : "text-rose-400 bg-rose-950/40 border-rose-900";

  return (
    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-700 bg-slate-900 px-4 py-3 text-slate-300 shadow-inner">
      <div className="flex items-center gap-2">
        <ShieldAlert className="h-4 w-4 text-emerald-400" />
        <span className="font-headline text-xs font-semibold">CogniGuard Risk Engine</span>
      </div>
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-slate-400">Trust Score:</span>
          <span className={`rounded border px-2 py-0.5 font-mono font-bold ${tone}`}>{trustScore.toFixed(0)}/100</span>
        </div>
        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-slate-400">Behavioral Match:</span>
          <span className={`rounded border px-2 py-0.5 font-mono font-bold ${behaviorMatch == null ? "border-slate-700 bg-slate-800 text-slate-400" : matchTone}`}>
            {behaviorMatch == null ? "calibrating…" : `${behaviorMatch.toFixed(0)}%`}
          </span>
        </div>
      </div>
    </div>
  );
}
