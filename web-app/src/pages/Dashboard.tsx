import { useLocation, useNavigate } from "react-router-dom";

import type { EnrollmentProgress } from "../api";
import CalibrationBanner from "../components/CalibrationBanner";
import TrustBadge from "../components/TrustBadge";

interface DashboardState {
  username?: string;
  trustScore?: number | null;
  behaviorMatch?: number | null;
  enrollment?: EnrollmentProgress | null;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const location = useLocation();
  const state = (location.state as DashboardState | null) ?? {};
  const username = state.username ?? "genuine";

  return (
    <div className="mx-auto mt-16 max-w-md rounded border p-6 shadow-sm">
      <h1 className="text-xl font-semibold">Welcome, {username}</h1>
      {/* CogniGuard is a risk-orchestration layer, not a ledger (PRD non-goals) -- this
          is a static demo balance; the bank's core system holds the real one. */}
      <p className="mt-2 text-3xl font-bold">₹1,00,000.00</p>
      <p className="text-sm text-gray-500">Savings account</p>

      <CalibrationBanner progress={state.enrollment} />
      <TrustBadge trustScore={state.trustScore} behaviorMatch={state.behaviorMatch} />

      <button
        type="button"
        className="mt-6 w-full rounded bg-blue-600 px-3 py-2 text-white"
        onClick={() => navigate("/transfer", { state: { username } })}
      >
        Transfer funds
      </button>
    </div>
  );
}
