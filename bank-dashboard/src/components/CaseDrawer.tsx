import { Fragment, useState } from "react";

import { type CaseOut, type CaseStatus, patchCase } from "../api";
import InvestigationAssistant from "./InvestigationAssistant";
import SHAPExplainer from "./SHAPExplainer";

interface CaseDrawerProps {
  caseItem: CaseOut;
  onClose: () => void;
  onUpdated: (updated: CaseOut) => void;
  latestScoreId?: string | null;
}

const STATUSES: CaseStatus[] = [
  "open",
  "investigating",
  "confirmed_fraud",
  "false_positive",
  "closed",
];

type DrawerTab = "details" | "shap" | "investigate";

export default function CaseDrawer({ caseItem, onClose, onUpdated, latestScoreId }: CaseDrawerProps) {
  const [status, setStatus] = useState<CaseStatus>(caseItem.status);
  const [assignedTo, setAssignedTo] = useState(caseItem.assigned_to ?? "");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<DrawerTab>("details");

  async function save() {
    setBusy(true);
    try {
      const { body } = await patchCase(caseItem.case_id, {
        status,
        assigned_to: assignedTo,
        note,
      });
      onUpdated(body);
    } finally {
      setBusy(false);
    }
  }

  const tabs: Array<{ key: DrawerTab; label: string }> = [
    { key: "details", label: "Details" },
    { key: "investigate", label: "AI Investigate" },
    ...(latestScoreId ? [{ key: "shap" as DrawerTab, label: "SHAP" }] : []),
  ];

  return (
    <div className="fixed inset-y-0 right-0 z-30 flex w-full max-w-md flex-col border-l border-soc-border bg-soc-surface shadow-xl overflow-y-auto">
      {/* Drawer header */}
      <div className="flex items-center justify-between border-b border-soc-border px-5 py-4">
        <div>
          <h2 className="font-headline text-base font-bold text-soc-text">Case Details</h2>
          <p className="font-mono mt-0.5 text-xs text-soc-muted">{caseItem.case_id.slice(0, 16)}…</p>
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

      {/* Tabs */}
      <div className="flex gap-1 border-b border-soc-border px-5 pt-3">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`mb-[-1px] pb-2.5 px-3 text-xs font-semibold border-b-2 transition-colors ${
              tab === t.key
                ? "border-soc-primary text-soc-primary"
                : "border-transparent text-soc-muted hover:text-soc-text"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "details" && (
        <div className="flex-1 space-y-4 p-5 text-sm">
          {/* Info grid */}
          <div className="rounded-xl border border-soc-border bg-soc-elevated p-4">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5 text-xs">
              {[
                ["Alert type", caseItem.alert_type ?? "—"],
                ["Severity", caseItem.severity ?? "—"],
                ["Risk band", caseItem.risk_band?.replace("_", " ") ?? "—"],
                ["Risk score", caseItem.final_risk_score != null ? caseItem.final_risk_score.toFixed(1) : "—"],
                ["User", caseItem.user_id?.slice(0, 12) ?? "—"],
                ["Transaction", caseItem.transaction_id?.slice(0, 12) ?? "—"],
                ["Opened", caseItem.created_at ? new Date(caseItem.created_at).toLocaleString("en-IN") : "—"],
              ].map(([label, value]) => (
                <Fragment key={label}>
                  <dt className="text-soc-muted">{label}</dt>
                  <dd className="truncate font-medium text-soc-text">{value}</dd>
                </Fragment>
              ))}
            </dl>
          </div>

          {/* Reason codes */}
          {caseItem.reason_codes && caseItem.reason_codes.length > 0 && (
            <div className="rounded-xl border border-soc-border bg-soc-elevated p-4">
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-soc-muted">Reason Codes</p>
              <div className="flex flex-wrap gap-1.5">
                {caseItem.reason_codes.map((rc, i) => (
                  <span key={i} className="rounded-full bg-soc-warning-light px-2.5 py-0.5 text-[10px] font-bold text-soc-warning">
                    {String((rc as Record<string, unknown>)["code"] ?? rc)}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Amplifiers */}
          {caseItem.amplifiers && caseItem.amplifiers.length > 0 && (
            <div className="rounded-xl border border-soc-border bg-soc-elevated p-4">
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-soc-muted">Risk Amplifiers</p>
              <div className="space-y-1.5">
                {caseItem.amplifiers.map((amp, i) => {
                  const a = amp as Record<string, unknown>;
                  return (
                    <div key={i} className="flex items-start gap-2 text-xs">
                      <span className="shrink-0 rounded-full bg-soc-danger-light px-2.5 py-0.5 text-[10px] font-bold text-soc-danger">
                        {String(a["code"] ?? "")} ×{Number(a["multiplier"] ?? 1).toFixed(1)}
                      </span>
                      <span className="text-soc-muted">{String(a["detail"] ?? "")}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <div>
            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-soc-muted">Status</label>
            <select
              className="w-full rounded-lg border border-soc-border bg-soc-bg px-3 py-2 text-sm text-soc-text outline-none focus:border-soc-primary"
              value={status}
              onChange={(e) => setStatus(e.target.value as CaseStatus)}
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>{s.replace("_", " ")}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-soc-muted">Assigned To</label>
            <input
              className="w-full rounded-lg border border-soc-border bg-soc-bg px-3 py-2 text-sm text-soc-text outline-none focus:border-soc-primary"
              value={assignedTo}
              placeholder="analyst@bank.in"
              onChange={(e) => setAssignedTo(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-soc-muted">Note</label>
            <textarea
              className="w-full rounded-lg border border-soc-border bg-soc-bg px-3 py-2 text-sm text-soc-text outline-none focus:border-soc-primary"
              rows={3}
              value={note}
              placeholder="Add investigation notes…"
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
          <button
            type="button"
            disabled={busy}
            className="w-full rounded-lg bg-soc-primary py-2.5 text-sm font-bold text-white transition-all hover:bg-cbi-primary-dark disabled:opacity-50"
            onClick={() => void save()}
          >
            {busy ? "Saving…" : "Save Changes"}
          </button>
        </div>
      )}

      {tab === "investigate" && (
        <div className="mt-4">
          <InvestigationAssistant caseId={caseItem.case_id} />
        </div>
      )}

      {tab === "shap" && latestScoreId && (
        <div className="mt-4">
          <SHAPExplainer scoreId={latestScoreId} />
        </div>
      )}
    </div>
  );
}
