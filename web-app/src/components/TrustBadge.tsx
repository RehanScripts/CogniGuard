import { ShieldCheck } from "lucide-react";

export default function TrustBadge({
  trustScore,
  behaviorMatch,
}: {
  trustScore?: number | null;
  behaviorMatch?: number | null;
}) {
  if (trustScore == null) return null;

  const identityLabel =
    trustScore > 80 ? "Verified" : trustScore > 40 ? "Monitoring" : "Reviewing";
  const identityTone =
    trustScore > 80
      ? "text-emerald-700 bg-emerald-50 border-emerald-200"
      : trustScore > 40
        ? "text-amber-700 bg-amber-50 border-amber-200"
        : "text-rose-700 bg-rose-50 border-rose-200";

  const behaviorLabel =
    behaviorMatch == null ? "Calibrating" : behaviorMatch > 80 ? "Active" : "Reviewing";
  const behaviorTone =
    behaviorMatch == null
      ? "text-slate-500 bg-slate-100 border-slate-200"
      : behaviorMatch > 80
        ? "text-emerald-700 bg-emerald-50 border-emerald-200"
        : "text-rose-700 bg-rose-50 border-rose-200";

  return (
    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 text-slate-700 shadow-sm">
      <div className="flex items-center gap-2">
        <ShieldCheck className="h-4 w-4 text-emerald-600" />
        <span className="text-xs font-semibold">Security Status</span>
      </div>
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-slate-500">Identity:</span>
          <span className={`rounded border px-2 py-0.5 font-semibold ${identityTone}`}>{identityLabel}</span>
        </div>
        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-slate-500">Behavioral verification:</span>
          <span className={`rounded border px-2 py-0.5 font-semibold ${behaviorTone}`}>{behaviorLabel}</span>
        </div>
      </div>
    </div>
  );
}
