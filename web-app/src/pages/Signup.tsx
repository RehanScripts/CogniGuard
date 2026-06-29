import {
  AlertOctagon,
  ArrowRight,
  CheckCircle,
  Eye,
  EyeOff,
  Lock,
  Mail,
  Shield,
  User,
} from "lucide-react";
import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { register, setConsent } from "../api";
import logo from "../assets/logo.jpeg";

function passwordStrength(pw: string): { label: string; color: string; width: string } {
  if (pw.length === 0) return { label: "", color: "bg-slate-200", width: "w-0" };
  let score = 0;
  if (pw.length >= 8) score++;
  if (/[A-Z]/.test(pw)) score++;
  if (/[0-9]/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  const levels = [
    { label: "Weak", color: "bg-red-500", width: "w-1/4" },
    { label: "Fair", color: "bg-amber-500", width: "w-2/4" },
    { label: "Good", color: "bg-yellow-400", width: "w-3/4" },
    { label: "Strong", color: "bg-emerald-500", width: "w-full" },
  ];
  return levels[Math.min(score, 3)];
}

export default function Signup() {
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [consent, setConsentChecked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const strength = passwordStrength(password);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (!consent) {
      setError("Please accept the data processing consent to continue.");
      return;
    }

    setBusy(true);
    try {
      const regRes = await register(username, password, email || undefined, fullName || undefined);
      if (regRes.status !== 201) {
        setError(
          (regRes.body as { detail?: string }).detail ?? "Registration failed. Username may already exist.",
        );
        return;
      }
      await setConsent(username, "GRANT");
      navigate("/login", { state: { registered: true } });
    } catch {
      setError("Could not reach the server. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative flex min-h-screen flex-col overflow-hidden bg-background-custom font-sans">
      <div
        className="pointer-events-none absolute inset-0 z-0 opacity-10"
        style={{
          backgroundImage:
            "radial-gradient(circle at 2px 2px, #c1c7d3 1px, transparent 0)",
          backgroundSize: "24px 24px",
        }}
      />

      <div className="z-10 flex flex-grow items-center justify-center px-4 py-12 md:px-8">
        <div className="w-full max-w-[440px]">
          <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-8 shadow-xl md:p-10">
            <div className="mb-8 flex flex-col items-center">
              <span className="mb-4 flex h-16 w-16 items-center justify-center overflow-hidden rounded-full bg-white p-2 shadow-md">
                <img src={logo} alt="Central Bank of India" className="h-full w-full object-contain" />
              </span>
              <h1 className="font-headline text-2xl font-bold tracking-tight text-primary">
                Create Account
              </h1>
              <p className="mt-1 text-center text-xs font-medium uppercase tracking-widest text-on-surface-variant">
                Central Bank of India
              </p>
            </div>

            {error && (
              <div className="mb-6 flex gap-3 rounded-lg border border-rose-200 bg-rose-50 p-4 text-xs leading-relaxed text-rose-800">
                <AlertOctagon className="mt-0.5 h-5 w-5 shrink-0 text-rose-600" />
                <p className="font-semibold text-rose-900">{error}</p>
              </div>
            )}

            <form className="space-y-4" onSubmit={handleSubmit}>
              <div className="space-y-1.5">
                <label className="block text-xs font-semibold text-on-surface-variant" htmlFor="full_name">
                  Full name
                </label>
                <div className="group relative rounded-lg">
                  <User className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-outline transition-colors group-focus-within:text-primary" />
                  <input
                    id="full_name"
                    type="text"
                    className="w-full rounded-lg border border-outline-variant bg-white py-3 pl-10 pr-4 text-sm outline-none transition-all placeholder:text-slate-300 focus:border-primary focus:ring-1 focus:ring-primary"
                    placeholder="Your name"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="block text-xs font-semibold text-on-surface-variant" htmlFor="email">
                  Email address
                </label>
                <div className="group relative rounded-lg">
                  <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-outline transition-colors group-focus-within:text-primary" />
                  <input
                    id="email"
                    type="email"
                    className="w-full rounded-lg border border-outline-variant bg-white py-3 pl-10 pr-4 text-sm outline-none transition-all placeholder:text-slate-300 focus:border-primary focus:ring-1 focus:ring-primary"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </div>
                <p className="text-[11px] text-on-surface-variant">
                  Used for OTP delivery during step-up authentication.
                </p>
              </div>

              <div className="space-y-1.5">
                <label className="block text-xs font-semibold text-on-surface-variant" htmlFor="username">
                  Username
                </label>
                <div className="group relative rounded-lg">
                  <User className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-outline transition-colors group-focus-within:text-primary" />
                  <input
                    id="username"
                    type="text"
                    required
                    className="w-full rounded-lg border border-outline-variant bg-white py-3 pl-10 pr-4 text-sm outline-none transition-all placeholder:text-slate-300 focus:border-primary focus:ring-1 focus:ring-primary"
                    placeholder="Choose a username"
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
                    type={showPassword ? "text" : "password"}
                    required
                    className="w-full rounded-lg border border-outline-variant bg-white py-3 pl-10 pr-10 text-sm outline-none transition-all placeholder:text-slate-300 focus:border-primary focus:ring-1 focus:ring-primary"
                    placeholder="At least 8 characters"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-outline hover:text-on-surface"
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                {password.length > 0 && (
                  <div className="mt-1">
                    <div className="h-1 w-full overflow-hidden rounded-full bg-slate-100">
                      <div className={`h-full rounded-full transition-all ${strength.color} ${strength.width}`} />
                    </div>
                    <p className={`mt-0.5 text-[11px] font-medium ${strength.color.replace("bg-", "text-")}`}>
                      {strength.label}
                    </p>
                  </div>
                )}
              </div>

              <div className="space-y-1.5">
                <label className="block text-xs font-semibold text-on-surface-variant" htmlFor="confirm_password">
                  Confirm password
                </label>
                <div className="group relative rounded-lg">
                  <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-outline transition-colors group-focus-within:text-primary" />
                  <input
                    id="confirm_password"
                    type={showPassword ? "text" : "password"}
                    required
                    className="w-full rounded-lg border border-outline-variant bg-white py-3 pl-10 pr-4 text-sm outline-none transition-all placeholder:text-slate-300 focus:border-primary focus:ring-1 focus:ring-primary"
                    placeholder="Re-enter password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                  />
                </div>
              </div>

              {/* DPDP consent */}
              <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-outline-variant bg-slate-50 p-3 text-xs text-on-surface-variant">
                <input
                  type="checkbox"
                  className="mt-0.5 accent-primary"
                  checked={consent}
                  onChange={(e) => setConsentChecked(e.target.checked)}
                />
                <span>
                  I consent to Heritage Trust Bank collecting and processing my behavioral data for
                  security and fraud prevention purposes under the{" "}
                  <strong>Digital Personal Data Protection Act 2023</strong>. I understand I can
                  withdraw consent at any time in Security settings.
                </span>
              </label>

              <button
                type="submit"
                disabled={busy || !username || !password}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary py-3.5 text-sm font-bold text-on-primary shadow-md transition-all hover:bg-primary-container active:scale-[0.99] disabled:cursor-not-allowed disabled:bg-slate-300"
              >
                {busy ? (
                  <span className="flex items-center gap-2">
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                    Creating account…
                  </span>
                ) : (
                  <>
                    <span>Create Account</span>
                    <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </button>
            </form>

            <div className="mt-5 text-center text-xs text-on-surface-variant">
              Already have an account?{" "}
              <button
                type="button"
                className="font-semibold text-primary hover:underline"
                onClick={() => navigate("/login")}
              >
                Sign in
              </button>
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
