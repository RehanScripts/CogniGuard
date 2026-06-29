import { Clock, MonitorSmartphone, ShieldCheck, ShieldOff } from "lucide-react";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import {
  type ActiveSessionOut,
  type LoginHistoryOut,
  type TrustedDeviceOut,
  getLoginHistory,
  getSecuritySettings,
  getSessionToken,
  revokeSession,
  trustDevice,
} from "../api";
import AppHeader from "../components/AppHeader";
import Footer from "../components/Footer";

export default function Security() {
  const navigate = useNavigate();
  const location = useLocation();
  const username = (location.state as { username?: string } | null)?.username ?? "genuine";

  const [devices, setDevices] = useState<TrustedDeviceOut[]>([]);
  const [sessions, setSessions] = useState<ActiveSessionOut[]>([]);
  const [history, setHistory] = useState<LoginHistoryOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    const token = getSessionToken();
    if (!token) {
      navigate("/login");
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const [settingsRes, historyRes] = await Promise.all([
          getSecuritySettings(token),
          getLoginHistory(token),
        ]);
        if (cancelled) return;
        if (settingsRes.status === 200) {
          setDevices(settingsRes.body.trusted_devices);
          setSessions(settingsRes.body.active_sessions);
        }
        if (historyRes.status === 200) {
          setHistory(historyRes.body);
        }
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

  async function handleTrustDevice(deviceId: string) {
    const token = getSessionToken();
    if (!token) return;
    setActionError(null);
    try {
      const res = await trustDevice(token, deviceId);
      if (res.status === 200) {
        setDevices((prev) =>
          prev.map((d) => (d.device_id === deviceId ? { ...d, is_trusted: true } : d)),
        );
      } else {
        setActionError("Failed to trust device.");
      }
    } catch {
      setActionError("Failed to trust device.");
    }
  }

  async function handleRevokeSession(sessionId: string) {
    const token = getSessionToken();
    if (!token) return;
    setActionError(null);
    try {
      const res = await revokeSession(token, sessionId);
      if (res.status === 204) {
        setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
      } else {
        setActionError("Failed to revoke session.");
      }
    } catch {
      setActionError("Failed to revoke session.");
    }
  }

  function decisionBadge(decision: string | null) {
    if (!decision) return null;
    const map: Record<string, string> = {
      allow: "bg-emerald-50 text-emerald-700",
      verify: "bg-amber-50 text-amber-700",
      block: "bg-red-50 text-red-700",
    };
    return (
      <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${map[decision] ?? "bg-slate-100 text-slate-600"}`}>
        {decision}
      </span>
    );
  }

  return (
    <div className="flex min-h-screen flex-col bg-background-custom">
      <AppHeader username={username} />
      <div className="mx-auto mt-8 w-full max-w-md flex-1 px-4 pb-8">
        <button
          type="button"
          className="mb-4 text-sm font-medium text-primary"
          onClick={() => navigate("/dashboard", { state: { username } })}
        >
          ← Back to dashboard
        </button>

        {actionError && (
          <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
            {actionError}
          </div>
        )}

        <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-6 shadow-sm">
          <h1 className="font-headline text-xl font-bold text-on-surface">Security Center</h1>
          {loading && <p className="mt-2 text-sm text-on-surface-variant">Loading…</p>}
          {error && <p className="mt-2 text-sm text-secondary">{error}</p>}

          {!loading && (
            <>
              {/* Trusted Devices */}
              <h2 className="mb-2 mt-5 text-xs font-bold uppercase tracking-wider text-on-surface-variant">
                Trusted devices
              </h2>
              {devices.length === 0 ? (
                <p className="text-sm text-on-surface-variant">No devices on record.</p>
              ) : (
                <div className="overflow-hidden rounded-lg border border-outline-variant">
                  {devices.map((d) => (
                    <div
                      key={d.device_id}
                      className="flex items-center justify-between gap-3 border-t border-outline-variant px-3 py-3 first:border-t-0"
                    >
                      <div className="flex items-center gap-3">
                        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/10 text-primary">
                          <MonitorSmartphone className="h-4 w-4" />
                        </div>
                        <span className="text-sm text-on-surface">{d.label ?? d.device_id}</span>
                      </div>
                      {d.is_trusted ? (
                        <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[10px] font-bold text-emerald-600">
                          Trusted
                        </span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => handleTrustDevice(d.device_id)}
                          className="rounded-full bg-primary/10 px-3 py-1 text-[11px] font-semibold text-primary hover:bg-primary/20"
                        >
                          Trust
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Active Sessions */}
              <h2 className="mb-2 mt-6 text-xs font-bold uppercase tracking-wider text-on-surface-variant">
                Active sessions
              </h2>
              {sessions.length === 0 ? (
                <p className="text-sm text-on-surface-variant">No active sessions.</p>
              ) : (
                <div className="overflow-hidden rounded-lg border border-outline-variant">
                  {sessions.map((s) => (
                    <div
                      key={s.session_id}
                      className="flex items-center justify-between gap-3 border-t border-outline-variant px-3 py-3 first:border-t-0"
                    >
                      <div className="flex items-center gap-3">
                        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-emerald-50 text-emerald-600">
                          <ShieldCheck className="h-4 w-4" />
                        </div>
                        <div>
                          <p className="text-sm text-on-surface">{s.device_label ?? "Unknown device"}</p>
                          {s.location && (
                            <p className="text-xs text-on-surface-variant">{s.location}</p>
                          )}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleRevokeSession(s.session_id)}
                        className="flex items-center gap-1 rounded-full bg-red-50 px-3 py-1 text-[11px] font-semibold text-red-600 hover:bg-red-100"
                      >
                        <ShieldOff className="h-3 w-3" />
                        Revoke
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* Login History */}
              <h2 className="mb-2 mt-6 text-xs font-bold uppercase tracking-wider text-on-surface-variant">
                Login history
              </h2>
              {history.length === 0 ? (
                <p className="text-sm text-on-surface-variant">No login history available.</p>
              ) : (
                <div className="overflow-hidden rounded-lg border border-outline-variant">
                  {history.map((h) => (
                    <div
                      key={h.event_id}
                      className="flex items-center justify-between gap-3 border-t border-outline-variant px-3 py-3 first:border-t-0"
                    >
                      <div className="flex items-center gap-3">
                        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 text-slate-500">
                          <Clock className="h-4 w-4" />
                        </div>
                        <div>
                          <p className="text-sm text-on-surface">{h.device_label ?? "Unknown device"}</p>
                          <p className="text-xs text-on-surface-variant">
                            {h.event_type ?? "login"}{" "}
                            {h.created_at ? `· ${new Date(h.created_at).toLocaleString()}` : ""}
                          </p>
                        </div>
                      </div>
                      {decisionBadge(h.decision)}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
      <Footer />
    </div>
  );
}
