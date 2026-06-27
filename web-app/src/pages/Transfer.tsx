import { CogniGuard } from "@cogniguard/behavior-sdk";
import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { getSessionToken } from "../api";
import AppHeader from "../components/AppHeader";
import Footer from "../components/Footer";
import Payment from "./Payment";

// Route shell for the money-movement area of the app: starts continuous re-scoring
// for the session (Implementation.md line 627) and hosts the actual transfer form.
export default function Transfer() {
  const navigate = useNavigate();
  const location = useLocation();
  const username = (location.state as { username?: string } | null)?.username ?? "genuine";
  const stopRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    const token = getSessionToken();
    if (!token) {
      navigate("/login");
      return;
    }
    // Known limitation: the SDK's continuous loop POSTs to /behavior/ingest itself
    // and does not surface the response back here, so a mid-session hijack's
    // {action:"verify",reauth:true} can't be observed through this hook -- demoing
    // that scenario requires POSTing ingest_hijack.json directly against
    // /behavior/ingest while this page is open (see PROGRESS.md / Phase 11 plan).
    stopRef.current = CogniGuard.startContinuous(token);
    return () => stopRef.current?.();
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
        <Payment />
      </div>
      <Footer />
    </div>
  );
}
