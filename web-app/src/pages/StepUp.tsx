import { type FormEvent, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { type ChallengeType, type StepUpChallenge, setSessionToken, verifyStepUp } from "../api";

interface StepUpLocationState {
  challenge: StepUpChallenge | null;
  requiredFactors: string[];
  username: string;
}

const OTP_LIKE: ChallengeType[] = ["OTP", "MPIN"];

export default function StepUp() {
  const navigate = useNavigate();
  const location = useLocation();
  const state = location.state as StepUpLocationState | null;
  const challenge = state?.challenge ?? null;

  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!challenge) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-b from-cbi-primary-light to-cbi-surface px-4">
        <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow">
          <p>
            No active step-up challenge.{" "}
            <a className="text-cbi-primary" href="/login">
              Return to login
            </a>
            .
          </p>
        </div>
      </div>
    );
  }

  const isOtpLike = OTP_LIKE.includes(challenge.challenge_type);

  const submit = async (assertion: string) => {
    setBusy(true);
    setError(null);
    try {
      const { body } = await verifyStepUp(challenge.challenge_id, assertion);
      if (body.action === "allow" && body.session_token) {
        setSessionToken(body.session_token);
        navigate("/dashboard", { state: { username: state?.username } });
        return;
      }
      setError("Incorrect code, try again.");
    } finally {
      setBusy(false);
    }
  };

  function handleOtpSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    void submit(code);
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-b from-cbi-primary-light to-cbi-surface px-4 py-16">
      <div className="mb-6 flex flex-col items-center gap-2">
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-cbi-primary text-lg font-bold text-white">
          CB
        </span>
        <p className="text-sm text-gray-500">Central Bank of India · Secure Banking</p>
      </div>
      <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow">
        <h1 className="text-xl font-semibold">Verify it's you</h1>
        <p className="mt-1 text-sm text-gray-600">
          Required factor: {challenge.challenge_type} ({challenge.assurance})
        </p>
        <p className="mt-2 text-xs text-gray-500">
          This extra check was triggered by our risk engine to keep your account safe.
        </p>

        {isOtpLike ? (
          <form className="mt-4 space-y-3" onSubmit={handleOtpSubmit}>
            {/* Demo OTP is always "123456" (gateway/app/config.py demo_otp). */}
            <input
              className="w-full rounded border px-2 py-1 focus:border-cbi-primary focus:outline-none"
              placeholder="123456"
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded bg-cbi-primary px-3 py-2 text-white hover:bg-cbi-primary-dark disabled:opacity-50"
            >
              Verify
            </button>
          </form>
        ) : (
          <button
            type="button"
            disabled={busy}
            className="mt-4 w-full rounded bg-cbi-primary px-3 py-2 text-white hover:bg-cbi-primary-dark disabled:opacity-50"
            onClick={() => void submit(`simulated-${challenge.challenge_type.toLowerCase()}`)}
          >
            Simulate {challenge.challenge_type}
          </button>
        )}

        {error && <p className="mt-3 text-sm text-cbi-accent">{error}</p>}
      </div>
    </div>
  );
}
