import { useState } from "react";

import { setConsent } from "../api";

interface ConsentToggleProps {
  username: string;
}

export default function ConsentToggle({ username }: ConsentToggleProps) {
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handle(action: "GRANT" | "WITHDRAW") {
    if (!username) return;
    setBusy(true);
    try {
      const { body } = await setConsent(username, action);
      setStatus(body.consent_status ?? null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="text-sm text-gray-600">
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={busy}
          className="rounded bg-gray-100 px-2 py-1"
          onClick={() => handle("GRANT")}
        >
          Grant behavioral consent
        </button>
        <button
          type="button"
          disabled={busy}
          className="rounded bg-gray-100 px-2 py-1"
          onClick={() => handle("WITHDRAW")}
        >
          Withdraw consent
        </button>
      </div>
      {status === "WITHDRAWN" && (
        <p className="mt-1 text-xs text-gray-500">
          Consent withdrawn. Your raw behavioral samples and per-user model will be purged by the
          compliance right-to-be-forgotten job -- this does not happen instantly.
        </p>
      )}
    </div>
  );
}
