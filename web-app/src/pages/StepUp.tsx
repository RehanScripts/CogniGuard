import { CheckCircle, Clock, HelpCircle, Info, Shield } from "lucide-react";
import { Fragment, type KeyboardEvent, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import {
  type ChallengeType,
  type StepUpChallenge,
  setSessionToken,
  verifyPaymentStepUp,
  verifyStepUp,
} from "../api";

interface StepUpLocationState {
  challenge: StepUpChallenge | null;
  requiredFactors: string[];
  username: string;
  // Login step-up (default) resumes a session via `session_token`; a transaction
  // step-up instead resumes the same pending transfer -- no session involved.
  entityType?: "login" | "transaction";
}

const OTP_LIKE: ChallengeType[] = ["OTP", "MPIN"];
const RESEND_SECONDS = 179;

export default function StepUp() {
  const navigate = useNavigate();
  const location = useLocation();
  const state = location.state as StepUpLocationState | null;
  const challenge = state?.challenge ?? null;

  const [otpFields, setOtpFields] = useState<string[]>(["", "", "", "", "", ""]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [timerCount, setTimerCount] = useState(RESEND_SECONDS);
  const otpRefs = useRef<(HTMLInputElement | null)[]>([]);

  useEffect(() => {
    const timer = setInterval(() => {
      setTimerCount((prev) => (prev <= 1 ? 0 : prev - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  if (!challenge) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background-custom px-4">
        <div className="w-full max-w-sm rounded-lg bg-surface-container-lowest p-6 shadow">
          <p>
            No active step-up challenge.{" "}
            <a className="text-primary" href="/login">
              Return to login
            </a>
            .
          </p>
        </div>
      </div>
    );
  }

  const isOtpLike = OTP_LIKE.includes(challenge.challenge_type);
  const entityType = state?.entityType ?? "login";

  const submit = async (assertion: string) => {
    setBusy(true);
    setError(null);
    try {
      if (entityType === "transaction") {
        const { body } = await verifyPaymentStepUp(challenge.challenge_id, assertion);
        if (body.action === "allow") {
          navigate("/transfer", { state: { username: state?.username, resolvedPayment: body } });
          return;
        }
        setError(body.action === "block" ? "Verification failed -- transfer blocked." : "Incorrect code, try again.");
        return;
      }
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

  function handleOtpChange(val: string, index: number) {
    const updated = [...otpFields];
    updated[index] = val.slice(-1);
    setOtpFields(updated);
    setError(null);
    if (val && index < 5) {
      otpRefs.current[index + 1]?.focus();
    }
  }

  function handleOtpKeyDown(e: KeyboardEvent<HTMLInputElement>, index: number) {
    if (e.key === "Backspace" && !otpFields[index] && index > 0) {
      otpRefs.current[index - 1]?.focus();
    }
  }

  function handleOtpSubmit() {
    void submit(otpFields.join(""));
  }

  function formatTime(secs: number) {
    const mins = Math.floor(secs / 60);
    const remaining = secs % 60;
    return `${mins.toString().padStart(2, "0")}:${remaining.toString().padStart(2, "0")}`;
  }

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center bg-background-custom px-4 py-12">
      <main className="z-10 w-full max-w-[480px]">
        <div className="flex flex-col items-center rounded-xl border border-t-4 border-outline-variant border-t-primary bg-surface-container-lowest p-8 shadow-lg">
          <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-full border border-slate-200 bg-slate-100">
            <Shield className="h-8 w-8 text-primary" />
          </div>

          <h1 className="font-headline mb-2 text-center text-2xl font-bold text-on-surface">Verify it's you</h1>
          <p className="mb-8 px-4 text-center text-xs leading-relaxed text-on-surface-variant">
            {isOtpLike
              ? "We've sent a 6-digit verification code to your registered mobile number ending in •••• 8291."
              : `Required factor: ${challenge.challenge_type} (${challenge.assurance})`}
          </p>

          {error && (
            <div className="mb-6 w-full rounded-lg border border-rose-100 bg-rose-50 p-3 text-center text-xs font-semibold text-rose-800">
              {error}
            </div>
          )}

          {isOtpLike ? (
            <>
              <div className="mb-6 flex gap-2.5 md:gap-3" id="otp-container">
                {otpFields.map((field, idx) => (
                  <Fragment key={idx}>
                    <input
                      ref={(el) => (otpRefs.current[idx] = el)}
                      type="text"
                      inputMode="numeric"
                      maxLength={1}
                      disabled={busy}
                      value={field}
                      onChange={(e) => handleOtpChange(e.target.value, idx)}
                      onKeyDown={(e) => handleOtpKeyDown(e, idx)}
                      className="h-14 w-12 rounded-lg border border-outline-variant bg-white text-center text-xl font-bold outline-none transition-all focus:border-primary focus:ring-1 focus:ring-primary"
                    />
                    {idx === 2 && (
                      <div className="flex w-2 items-center justify-center font-extrabold text-outline-variant">-</div>
                    )}
                  </Fragment>
                ))}
              </div>

              <div className="mb-4 w-full rounded border border-slate-200 bg-slate-100 px-3 py-1.5 text-center font-mono text-[11px] text-slate-500">
                Demo OTP code is: <span className="font-bold text-slate-800">123456</span>
              </div>

              <div className="mb-8 flex flex-col items-center gap-2">
                <div className="flex items-center gap-1.5 text-xs font-medium text-on-surface-variant">
                  <Clock className="h-4 w-4 text-outline" />
                  <span>Resend in</span>
                  <span className="font-mono font-bold text-on-surface">{formatTime(timerCount)}</span>
                </div>
                <button
                  type="button"
                  disabled={timerCount > 0}
                  onClick={() => setTimerCount(RESEND_SECONDS)}
                  className={`text-xs font-semibold transition-opacity ${
                    timerCount > 0 ? "cursor-not-allowed text-slate-400 opacity-50" : "text-primary hover:underline"
                  }`}
                >
                  Resend code
                </button>
              </div>

              <button
                type="button"
                onClick={handleOtpSubmit}
                disabled={busy}
                className="font-headline mb-4 w-full rounded-lg bg-primary py-4 font-bold text-on-primary shadow-md transition-all hover:scale-[1.01] hover:bg-primary-container active:scale-[0.99] disabled:bg-slate-300"
              >
                {busy ? "Verifying..." : "Verify"}
              </button>
            </>
          ) : (
            <button
              type="button"
              disabled={busy}
              className="mb-6 flex w-full items-center justify-center gap-2 rounded-lg bg-primary py-3.5 text-sm font-bold text-on-primary shadow-md transition-all hover:bg-primary-container disabled:opacity-50"
              onClick={() => void submit(`simulated-${challenge.challenge_type.toLowerCase()}`)}
            >
              <Shield className="h-4 w-4" />
              <span>{busy ? "Verifying..." : `Simulate ${challenge.challenge_type} Assertion`}</span>
            </button>
          )}

          <div className="flex gap-3 rounded-lg bg-slate-100 p-4 text-left">
            <Info className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
            <p className="text-xs leading-relaxed text-on-surface-variant">
              This extra check was triggered by our risk engine to keep your account safe.
            </p>
          </div>
        </div>

        <div className="mt-6 flex justify-between px-2 text-xs">
          <a
            href={entityType === "transaction" ? "/transfer" : "/login"}
            className="flex items-center gap-1 text-on-surface-variant hover:text-primary"
          >
            <HelpCircle className="h-4 w-4" />
            <span>{entityType === "transaction" ? "Return to transfer" : "Return to login"}</span>
          </a>
          <div className="flex items-center gap-1 text-on-surface-variant">
            <CheckCircle className="h-4 w-4 text-emerald-600" />
            <span>PCI-DSS Secured</span>
          </div>
        </div>
      </main>
    </div>
  );
}
