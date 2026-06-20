import { useState } from "react";

import { type CaseOut, type CaseStatus, patchCase } from "../api";

interface CaseDrawerProps {
  caseItem: CaseOut;
  onClose: () => void;
  onUpdated: (updated: CaseOut) => void;
}

const STATUSES: CaseStatus[] = ["open", "investigating", "confirmed_fraud", "false_positive", "closed"];

export default function CaseDrawer({ caseItem, onClose, onUpdated }: CaseDrawerProps) {
  const [status, setStatus] = useState<CaseStatus>(caseItem.status);
  const [assignedTo, setAssignedTo] = useState(caseItem.assigned_to ?? "");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      const { body } = await patchCase(caseItem.case_id, { status, assigned_to: assignedTo, note });
      onUpdated(body);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-y-0 right-0 w-96 border-l bg-white p-4 shadow-lg">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Case {caseItem.case_id.slice(0, 8)}</h2>
        <button type="button" onClick={onClose} className="text-gray-400" aria-label="Close">
          ✕
        </button>
      </div>
      <div className="mt-4 space-y-3 text-sm">
        <label className="block">
          Status
          <select
            className="mt-1 w-full rounded border px-2 py-1"
            value={status}
            onChange={(e) => setStatus(e.target.value as CaseStatus)}
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          Assigned to
          <input
            className="mt-1 w-full rounded border px-2 py-1"
            value={assignedTo}
            onChange={(e) => setAssignedTo(e.target.value)}
          />
        </label>
        <label className="block">
          Note
          <textarea
            className="mt-1 w-full rounded border px-2 py-1"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
        <button
          type="button"
          disabled={busy}
          className="w-full rounded bg-blue-600 px-3 py-2 text-white disabled:opacity-50"
          onClick={() => void save()}
        >
          Save
        </button>
      </div>
    </div>
  );
}
