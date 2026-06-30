import { Lock, Shield } from "lucide-react";
import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { adminLogin, setAdminToken } from "../api";

export default function AdminLogin() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const { status, body } = await adminLogin(email, password);
      if (status !== 200) {
        setError("Invalid email or password.");
        return;
      }
      setAdminToken(body.token);
      navigate("/");
    } catch {
      setError("Could not reach CogniGuard. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-soc-bg px-4">
      <div className="w-full max-w-sm">
        {/* Header */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-soc-primary text-white shadow-lg">
            <Shield className="h-7 w-7" />
          </div>
          <h1 className="font-headline text-2xl font-bold text-soc-text">CogniGuard SOC</h1>
          <p className="mt-1 text-sm text-soc-muted">Central Bank of India · Fraud Operations</p>
        </div>

        {/* Card */}
        <div className="card p-6">
          <h2 className="mb-5 text-base font-semibold text-soc-text">Sign in to SOC Portal</h2>
          <form className="space-y-4" onSubmit={handleSubmit}>
            <div>
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-soc-muted" htmlFor="email">
                Email Address
              </label>
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                className="w-full rounded-lg border border-soc-border bg-soc-bg px-3 py-2.5 text-sm text-soc-text placeholder-soc-muted outline-none transition-colors focus:border-soc-primary focus:ring-1 focus:ring-soc-primary/20"
                placeholder="analyst@bank.in"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-soc-muted" htmlFor="password">
                Password
              </label>
              <div className="relative">
                <input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  className="w-full rounded-lg border border-soc-border bg-soc-bg py-2.5 pl-3 pr-10 text-sm text-soc-text placeholder-soc-muted outline-none transition-colors focus:border-soc-primary focus:ring-1 focus:ring-soc-primary/20"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <Lock className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-soc-muted/60" />
              </div>
            </div>

            {error && (
              <div className="rounded-lg border border-soc-danger-light bg-soc-danger-light px-3 py-2.5 text-sm font-medium text-soc-danger">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-lg bg-soc-primary py-2.5 text-sm font-bold text-white transition-all hover:bg-cbi-primary-dark active:scale-[0.98] disabled:opacity-60"
            >
              {busy ? "Signing in…" : "Sign In"}
            </button>
          </form>
        </div>

        <p className="mt-6 text-center text-xs text-soc-muted">
          Restricted access · Central Bank of India Internal Systems
        </p>
      </div>
    </div>
  );
}
