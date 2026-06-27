import { CogniGuard } from "@cogniguard/behavior-sdk";
import { AlertOctagon, ArrowRight, CheckCircle, Clock, Eye, EyeOff, Lock, Shield, User } from "lucide-react";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  API_BASE,
  type DecisionResponse,
  type Hardening,
  login,
  setSessionToken,
} from "../api";
import logo from "../assets/logo.jpeg";
import CalibrationBanner from "../components/CalibrationBanner";
import ChannelSwitcher from "../components/ChannelSwitcher";
import ConsentToggle from "../components/ConsentToggle";
import TrustBadge from "../components/TrustBadge";

// Dev-only demo value mirroring the gateway's JWT_SECRET (see PROGRESS.md's
// documented known-gap note on behavior-sdk's signing scheme) -- accepted as a
// prototype simplification, not redesigned here.
const SIGNING_SECRET = import.meta.env.VITE_SIGNING_SECRET || "change_me_dev_only_super_secret";

export default function Login() {
  const navigate = useNavigate();
  const formRef = useRef<HTMLFormElement>(null);
  const [username, setUsername] = useState("genuine");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hardening, setHardening] = useState<Hardening | null>(null);
  const [lastResult, setLastResult] = useState<DecisionResponse | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    CogniGuard.init({ apiBase: API_BASE, signingSecret: SIGNING_SECRET });
    if (formRef.current) {
      CogniGuard.attach(formRef.current, { page: "login" });
    }
    return () => CogniGuard.detach();
  }, []);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setHardening(null);
    setBusy(true);
    try {
      const behavior = await CogniGuard.collect("LOGIN");
      const { body } = await login(username, password, behavior);
      setLastResult(body);

      const trust = {
        trustScore: body.trust_score,
        behaviorMatch: body.behavior_match_score,
        enrollment: body.enrollment,
      };
      if (body.action === "verify") {
        navigate("/step-up", {
          state: {
            challenge: body.step_up,
            requiredFactors: body.required_factors,
            username,
            ...trust,
          },
        });
        return;
      }
      if (body.action === "block") {
        setHardening(body.hardening);
        setError("Login denied.");
        return;
      }
      if (body.session_token) {
        setSessionToken(body.session_token);
      }
      navigate("/dashboard", { state: { username, ...trust } });
    } catch {
      setError("Could not reach CogniGuard. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative flex min-h-screen flex-col overflow-hidden bg-background-custom font-sans">
      {/* Subtle background pattern -- CSS-only, no external photo */}
      <div
        className="pointer-events-none absolute inset-0 z-0 opacity-10"
        style={{ backgroundImage: "radial-gradient(circle at 2px 2px, #c1c7d3 1px, transparent 0)", backgroundSize: "24px 24px" }}
      />

      {lastResult && (
        <div className="z-10 w-full px-4 pt-4">
          <div className="mx-auto max-w-6xl">
            <TrustBadge trustScore={lastResult.trust_score} behaviorMatch={lastResult.behavior_match_score} />
          </div>
        </div>
      )}

      <div className="z-10 flex flex-grow items-center justify-center px-4 py-12 md:px-8">
        <div className="flex w-full max-w-6xl flex-col items-center justify-center gap-8 lg:flex-row">
          {/* Login card */}
          <div className="w-full max-w-[440px] rounded-xl border border-outline-variant bg-surface-container-lowest p-8 shadow-xl transition-transform duration-300 hover:scale-[1.01] md:p-10">
            <div className="mb-8 flex flex-col items-center">
              <span className="mb-4 flex h-16 w-16 items-center justify-center overflow-hidden rounded-full bg-white p-2 shadow-md">
                <img src={logo} alt="Central Bank of India" className="h-full w-full object-contain" />
              </span>
              <h1 className="font-headline text-2xl font-bold tracking-tight text-primary">
                Central Bank of India
              </h1>
              <p className="mt-1 text-center text-xs font-medium uppercase tracking-widest text-on-surface-variant">
                Secure Portal Access
              </p>
            </div>

            {error && (
              <div className="mb-6 flex gap-3 rounded-lg border border-rose-200 bg-rose-50 p-4 text-xs leading-relaxed text-rose-800">
                <AlertOctagon className="mt-0.5 h-5 w-5 shrink-0 text-rose-600" />
                <div>
                  <p className="font-semibold text-rose-900">{error}</p>
                  {hardening && (
                    <p className="mt-2 flex w-max items-center gap-1.5 rounded bg-rose-100/60 px-2 py-0.5 font-mono font-bold text-rose-700">
                      <Clock className="h-3.5 w-3.5" />
                      {hardening.action.toLowerCase()} &middot; retry after {hardening.retry_after_s}s
                    </p>
                  )}
                </div>
              </div>
            )}

            <form ref={formRef} className="space-y-5" onSubmit={handleSubmit}>
              <div className="space-y-1.5">
                <label className="block text-xs font-semibold text-on-surface-variant" htmlFor="username">
                  Username
                </label>
                <div className="group relative rounded-lg">
                  <User className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-outline transition-colors group-focus-within:text-primary" />
                  <input
                    id="username"
                    name="username"
                    className="w-full rounded-lg border border-outline-variant bg-white py-3 pl-10 pr-4 text-sm outline-none transition-all placeholder:text-slate-300 focus:border-primary focus:ring-1 focus:ring-primary"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="block text-xs font-semibold text-on-surface-variant" htmlFor="password">
                  Password
                </label>
                <div className="group relative rounded-lg">
                  <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-outline transition-colors group-focus-within:text-primary" />
                  <input
                    id="password"
                    name="password"
                    type={showPassword ? "text" : "password"}
                    className="w-full rounded-lg border border-outline-variant bg-white py-3 pl-10 pr-10 text-sm outline-none transition-all placeholder:text-slate-300 focus:border-primary focus:ring-1 focus:ring-primary"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-outline transition-colors hover:text-on-surface"
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              <div className="mt-2">
                <ChannelSwitcher />
              </div>

              <button
                type="submit"
                disabled={busy}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary py-3.5 text-sm font-bold text-on-primary shadow-md transition-all hover:bg-primary-container active:scale-[0.99] disabled:cursor-not-allowed disabled:bg-slate-300"
              >
                {busy ? (
                  <span className="flex items-center gap-2">
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                    Analyzing keystrokes...
                  </span>
                ) : (
                  <>
                    <span>Secure Login</span>
                    <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </button>
            </form>

            {lastResult && <CalibrationBanner progress={lastResult.enrollment} />}

            <div className="mt-6 border-t border-outline-variant pt-4">
              <ConsentToggle username={username} />
            </div>

            <div className="mt-6 flex items-center justify-center gap-4 border-t border-slate-100 pt-4 text-[10px] font-bold uppercase tracking-wider text-slate-500 opacity-70">
              <div className="flex items-center gap-1">
                <CheckCircle className="h-3.5 w-3.5 text-emerald-600" />
                <span>SSL Secured</span>
              </div>
              <div className="flex items-center gap-1">
                <Shield className="h-3.5 w-3.5 text-primary" />
                <span>256-Bit Encrypted</span>
              </div>
            </div>
          </div>

          {/* Right side: real-time behavioral capture status */}
          <div className="flex w-full max-w-sm flex-col gap-4">
            <div className="rounded-xl border border-slate-200 bg-white p-5 text-xs leading-relaxed text-slate-600 shadow-sm">
              <h3 className="font-headline mb-2 text-sm font-bold text-slate-900">CogniGuard Behavioral Engine</h3>
              <p>
                Every keystroke and pointer movement on this form is captured on-device and signed
                before submission. Your login is continuously risk-scored -- a genuine pattern
                signs straight in, an unfamiliar one triggers a step-up check, never a silent block.
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="z-10 mt-auto flex flex-wrap justify-center gap-4 border-t border-slate-200 bg-slate-100 py-4 text-center text-xs text-on-surface-variant">
        <button className="font-medium hover:text-primary">English</button>
        <span className="text-outline-variant">|</span>
        <button className="font-medium hover:text-primary">हिंदी</button>
        <span className="text-outline-variant">|</span>
        <button className="font-medium hover:text-primary">मराठी</button>
      </div>
    </div>
  );
}
