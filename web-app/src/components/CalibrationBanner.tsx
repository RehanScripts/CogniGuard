import type { EnrollmentProgress } from "../api";

// "Security Profile Calibration N/10" banner (gateway Phase 21). Progress accrues over
// the user's first ~N genuine logins; on the cycle that reaches `required` the per-user
// identity baseline is auto-generated (never seeded).
export default function CalibrationBanner({
  progress,
}: {
  progress: EnrollmentProgress | null | undefined;
}) {
  if (!progress) return null;

  if (progress.complete) {
    if (!progress.just_finalized) return null;
    return (
      <div className="mt-4 rounded border border-green-300 bg-green-50 p-3 text-sm text-green-800">
        ✓ Security profile calibrated — continuous identity verification is now active.
      </div>
    );
  }

  const pct = Math.round((progress.collected / progress.required) * 100);
  return (
    <div className="mt-4 rounded border border-cbi-primary-light bg-cbi-primary-light p-3">
      <div className="flex items-center justify-between text-sm text-cbi-primary-dark">
        <span>Security Profile Calibration</span>
        <span className="font-medium">
          {progress.collected}/{progress.required}
        </span>
      </div>
      <div className="mt-2 h-2 w-full overflow-hidden rounded bg-white">
        <div className="h-2 rounded bg-cbi-primary transition-all" style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-2 text-xs text-cbi-primary-dark">
        Learning your behavioral pattern. A few more genuine sign-ins and your profile is set.
      </p>
    </div>
  );
}
