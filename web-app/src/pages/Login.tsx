import { CogniGuard } from "@cogniguard/behavior-sdk";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { API_BASE, type Hardening, login, setSessionToken } from "../api";
import ChannelSwitcher from "../components/ChannelSwitcher";
import ConsentToggle from "../components/ConsentToggle";

// Dev-only demo value mirroring the gateway's JWT_SECRET (see PROGRESS.md's
// documented known-gap note on behavior-sdk's signing scheme) -- accepted as a
// prototype simplification, not redesigned here.
const SIGNING_SECRET = import.meta.env.VITE_SIGNING_SECRET || "change_me_dev_only_super_secret";

export default function Login() {
  const navigate = useNavigate();
  const formRef = useRef<HTMLFormElement>(null);
  const [username, setUsername] = useState("genuine");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [hardening, setHardening] = useState<Hardening | null>(null);
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

      if (body.action === "verify") {
        navigate("/step-up", {
          state: { challenge: body.step_up, requiredFactors: body.required_factors, username },
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
      navigate("/dashboard", { state: { username } });
    } catch {
      setError("Could not reach CogniGuard. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto mt-16 max-w-sm rounded border p-6 shadow-sm">
      <h1 className="text-xl font-semibold">CogniGuard Bank</h1>
      <div className="mt-2">
        <ChannelSwitcher />
      </div>
      <form ref={formRef} className="mt-4 space-y-3" onSubmit={handleSubmit}>
        <div>
          <label className="block text-sm text-gray-600" htmlFor="username">
            Username
          </label>
          <input
            id="username"
            name="username"
            className="mt-1 w-full rounded border px-2 py-1"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
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
            className="mt-1 w-full rounded border px-2 py-1"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded bg-blue-600 px-3 py-2 text-white disabled:opacity-50"
        >
          {busy ? "Signing in..." : "Sign in"}
        </button>
      </form>
      {error && (
        <p className="mt-3 text-sm text-red-600">
          {error}
          {hardening && ` (${hardening.action.toLowerCase()}, retry after ${hardening.retry_after_s}s)`}
        </p>
      )}
      <div className="mt-6 border-t pt-4">
        <ConsentToggle username={username} />
      </div>
    </div>
  );
}
