import { useNavigate } from "react-router-dom";

import type { EventRow } from "./EventTable";
import SHAPExplainer from "./SHAPExplainer";

interface EventDrawerProps {
  row: EventRow;
  onClose: () => void;
}

export default function EventDrawer({ row, onClose }: EventDrawerProps) {
  const navigate = useNavigate();

  return (
    <div className="fixed inset-y-0 right-0 z-30 flex w-full max-w-md flex-col border-l border-soc-border bg-soc-surface shadow-xl overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-soc-border px-5 py-4">
        <div>
          <h2 className="font-headline text-base font-bold text-soc-text capitalize">
            {row.entityType} Event
          </h2>
          <p className="font-mono mt-0.5 text-xs text-soc-muted">
            {row.entityId ? row.entityId.slice(0, 16) + "…" : row.key.slice(0, 16)}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-soc-muted transition-colors hover:bg-soc-bg hover:text-soc-text"
          aria-label="Close"
        >
          ✕
        </button>
      </div>

      {/* Quick meta */}
      <div className="border-b border-soc-border px-5 py-4">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
          <dt className="text-soc-muted">Risk Band</dt>
          <dd className="font-semibold text-soc-text capitalize">{row.band?.replace("_", " ") ?? "—"}</dd>
          <dt className="text-soc-muted">Score</dt>
          <dd className="font-mono font-semibold text-soc-text">{row.score != null ? row.score.toFixed(1) : "—"}</dd>
          <dt className="text-soc-muted">Action</dt>
          <dd className="font-semibold text-soc-text capitalize">{row.action ?? "—"}</dd>
          <dt className="text-soc-muted">Time</dt>
          <dd className="font-mono text-soc-text">{new Date(row.ts).toLocaleTimeString()}</dd>
          {row.userId && (
            <>
              <dt className="text-soc-muted">User</dt>
              <dd className="font-mono text-soc-text truncate">{row.userId.slice(0, 16)}…</dd>
            </>
          )}
        </dl>
        {row.userId && (
          <button
            type="button"
            onClick={() => { onClose(); navigate(`/users/${row.userId}`); }}
            className="mt-3 text-xs font-semibold text-soc-primary hover:underline"
          >
            View user profile →
          </button>
        )}
      </div>

      {/* AI Investigate / SHAP */}
      <div className="flex-1">
        {row.scoreId ? (
          <>
            <div className="px-5 pt-4 pb-2">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-soc-muted">
                AI Investigate
              </p>
              <p className="mt-1 text-xs text-soc-muted">
                Click below to explain why this event was scored and what actions are recommended.
              </p>
            </div>
            <SHAPExplainer scoreId={row.scoreId} />
          </>
        ) : (
          <div className="px-5 py-6 text-sm text-soc-muted">
            <p className="font-semibold text-soc-text mb-1">No score ID available</p>
            <p>This event came from a real-time WS stream without a persisted score reference. Scroll the feed — rows from the initial load carry full SHAP context.</p>
          </div>
        )}
      </div>
    </div>
  );
}
