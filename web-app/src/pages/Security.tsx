import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { type SecuritySettingsOut, getSecuritySettings, getSessionToken } from "../api";

export default function Security() {
  const navigate = useNavigate();
  const location = useLocation();
  const username = (location.state as { username?: string } | null)?.username ?? "genuine";

  const [settings, setSettings] = useState<SecuritySettingsOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getSessionToken();
    if (!token) {
      navigate("/login");
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await getSecuritySettings(token);
        if (cancelled) return;
        if (res.status === 200) setSettings(res.body);
      } catch {
        if (!cancelled) setError("Could not load security settings.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  return (
    <div className="mx-auto mt-16 max-w-md">
      <button
        type="button"
        className="mb-4 text-sm text-blue-600"
        onClick={() => navigate("/dashboard", { state: { username } })}
      >
        ← Back to dashboard
      </button>

      <div className="rounded border p-6 shadow-sm">
        <h1 className="text-xl font-semibold">Security settings</h1>
        {loading && <p className="mt-2 text-sm text-gray-500">Loading...</p>}
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

        {settings && (
          <>
            <h2 className="mt-4 text-sm font-semibold text-gray-700">Trusted devices</h2>
            {settings.trusted_devices.length === 0 && (
              <p className="mt-1 text-sm text-gray-500">No trusted devices.</p>
            )}
            <ul className="mt-2 space-y-2">
              {settings.trusted_devices.map((d) => (
                <li key={d.device_id} className="flex justify-between border-t pt-2 text-sm first:border-t-0 first:pt-0">
                  <span>{d.label ?? d.device_id}</span>
                  <span className="text-gray-500">{d.is_trusted ? "Trusted" : "Not trusted"}</span>
                </li>
              ))}
            </ul>

            <h2 className="mt-4 text-sm font-semibold text-gray-700">Active sessions</h2>
            {settings.active_sessions.length === 0 && (
              <p className="mt-1 text-sm text-gray-500">No active sessions.</p>
            )}
            <ul className="mt-2 space-y-2">
              {settings.active_sessions.map((s) => (
                <li key={s.session_id} className="flex justify-between border-t pt-2 text-sm first:border-t-0 first:pt-0">
                  <span>{s.device_label ?? s.session_id}</span>
                  <span className="text-gray-500">{s.location ?? "--"}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
