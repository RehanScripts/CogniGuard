import { MonitorSmartphone, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { type SecuritySettingsOut, getSecuritySettings, getSessionToken } from "../api";
import AppHeader from "../components/AppHeader";
import Footer from "../components/Footer";

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
    <div className="flex min-h-screen flex-col bg-background-custom">
      <AppHeader username={username} />
      <div className="mx-auto mt-8 w-full max-w-md flex-1 px-4">
        <button
          type="button"
          className="mb-4 text-sm font-medium text-primary"
          onClick={() => navigate("/dashboard", { state: { username } })}
        >
          ← Back to dashboard
        </button>

        <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-6 shadow-sm">
          <h1 className="font-headline text-xl font-bold text-on-surface">Security settings</h1>
          {loading && <p className="mt-2 text-sm text-on-surface-variant">Loading...</p>}
          {error && <p className="mt-2 text-sm text-secondary">{error}</p>}

          {settings && (
            <>
              <h2 className="mb-2 mt-5 text-xs font-bold uppercase tracking-wider text-on-surface-variant">Trusted devices</h2>
              {settings.trusted_devices.length === 0 ? (
                <p className="text-sm text-on-surface-variant">No trusted devices.</p>
              ) : (
                <div className="overflow-hidden rounded-lg border border-outline-variant">
                  {settings.trusted_devices.map((d) => (
                    <div key={d.device_id} className="flex items-center justify-between gap-3 border-t border-outline-variant px-3 py-3 first:border-t-0">
                      <div className="flex items-center gap-3">
                        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/10 text-primary">
                          <MonitorSmartphone className="h-4 w-4" />
                        </div>
                        <span className="text-sm text-on-surface">{d.label ?? d.device_id}</span>
                      </div>
                      <span
                        className={`rounded-full px-2.5 py-1 text-[10px] font-bold ${
                          d.is_trusted ? "bg-emerald-50 text-emerald-600" : "bg-slate-100 text-on-surface-variant"
                        }`}
                      >
                        {d.is_trusted ? "Trusted" : "Not trusted"}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              <h2 className="mb-2 mt-6 text-xs font-bold uppercase tracking-wider text-on-surface-variant">Active sessions</h2>
              {settings.active_sessions.length === 0 ? (
                <p className="text-sm text-on-surface-variant">No active sessions.</p>
              ) : (
                <div className="overflow-hidden rounded-lg border border-outline-variant">
                  {settings.active_sessions.map((s) => (
                    <div key={s.session_id} className="flex items-center justify-between gap-3 border-t border-outline-variant px-3 py-3 first:border-t-0">
                      <div className="flex items-center gap-3">
                        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-emerald-50 text-emerald-600">
                          <ShieldCheck className="h-4 w-4" />
                        </div>
                        <span className="text-sm text-on-surface">{s.device_label ?? s.session_id}</span>
                      </div>
                      <span className="text-xs text-on-surface-variant">{s.location ?? "--"}</span>
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
