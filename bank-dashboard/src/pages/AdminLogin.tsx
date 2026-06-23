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
    <div className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-b from-cbi-primary-light to-cbi-surface px-4 py-16">
      <div className="mb-6 flex flex-col items-center gap-2">
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-cbi-primary text-lg font-bold text-white">
          CB
        </span>
        <h1 className="text-xl font-semibold text-cbi-text">CogniGuard SOC</h1>
        <p className="text-sm text-gray-500">Central Bank of India · Fraud Operations</p>
      </div>
      <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow">
        <form className="mt-2 space-y-3" onSubmit={handleSubmit}>
          <div>
            <label className="block text-sm text-gray-600" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              name="email"
              type="email"
              className="mt-1 w-full rounded border px-2 py-1 focus:border-cbi-primary focus:outline-none"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm text-gray-600" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              className="mt-1 w-full rounded border px-2 py-1 focus:border-cbi-primary focus:outline-none"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded bg-cbi-primary px-3 py-2 text-white hover:bg-cbi-primary-dark disabled:opacity-50"
          >
            {busy ? "Signing in..." : "Sign in"}
          </button>
        </form>
        {error && <p className="mt-3 text-sm text-cbi-accent">{error}</p>}
      </div>
    </div>
  );
}
