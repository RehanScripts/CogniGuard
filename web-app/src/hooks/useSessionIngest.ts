import { CogniGuard } from "@cogniguard/behavior-sdk";
import { useEffect, useRef, useState } from "react";
import { type BehaviorIngestResponse, clearSessionToken, getSessionToken, ingestBehavior } from "../api";

export interface SessionIngestState {
  /** True when the server returned action="verify" — show a step-up prompt. */
  reauthRequired: boolean;
  /** True when the server terminated the session (reauth=true, very_high risk). */
  sessionTerminated: boolean;
  /** Last ingest response for detail display (optional). */
  lastResponse: BehaviorIngestResponse | null;
  /** Clear the reauth flag after the user dismisses/completes the step-up. */
  dismissReauth: () => void;
}

/**
 * Fires POST /behavior/ingest every `intervalMs` while the component is mounted.
 * On action="verify" sets reauthRequired; on reauth=true (session terminated by
 * the gateway) sets sessionTerminated so the caller can redirect to /login.
 */
export function useSessionIngest(intervalMs = 30_000): SessionIngestState {
  const [reauthRequired, setReauthRequired] = useState(false);
  const [sessionTerminated, setSessionTerminated] = useState(false);
  const [lastResponse, setLastResponse] = useState<BehaviorIngestResponse | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const tick = async () => {
      const token = getSessionToken();
      if (!token) return;
      try {
        const payload = await CogniGuard.collect("VIEW_BALANCE");
        const res = await ingestBehavior(token, payload);
        if (res.status === 200) {
          setLastResponse(res.body);
          if (res.body.reauth) {
            clearSessionToken();
            setSessionTerminated(true);
          } else if (res.body.action === "verify") {
            setReauthRequired(true);
          }
        }
      } catch {
        // Best-effort: a failed tick doesn't kill the loop.
      }
    };

    timerRef.current = setInterval(tick, intervalMs);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [intervalMs]);

  const dismissReauth = () => setReauthRequired(false);

  return { reauthRequired, sessionTerminated, lastResponse, dismissReauth };
}
