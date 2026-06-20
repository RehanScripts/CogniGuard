import { useEffect, useState } from "react";

import { type CaseOut, listCases } from "../api";
import CaseDrawer from "../components/CaseDrawer";

export default function Cases() {
  const [cases, setCases] = useState<CaseOut[]>([]);
  const [selected, setSelected] = useState<CaseOut | null>(null);

  function refresh() {
    listCases({ limit: 100 })
      .then(({ body }) => setCases(body))
      .catch(() => undefined);
  }

  useEffect(() => {
    refresh();
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Cases</h1>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-gray-500">
            <th className="py-1">Case</th>
            <th>Status</th>
            <th>Severity</th>
            <th>Assigned</th>
          </tr>
        </thead>
        <tbody>
          {cases.map((c) => (
            <tr
              key={c.case_id}
              className="cursor-pointer border-t hover:bg-gray-50"
              onClick={() => setSelected(c)}
            >
              <td className="py-1">{c.case_id.slice(0, 8)}</td>
              <td>{c.status}</td>
              <td>{c.severity ?? "--"}</td>
              <td>{c.assigned_to ?? "--"}</td>
            </tr>
          ))}
          {cases.length === 0 && (
            <tr>
              <td colSpan={4} className="py-4 text-center text-gray-400">
                No cases
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {selected && (
        <CaseDrawer
          caseItem={selected}
          onClose={() => setSelected(null)}
          onUpdated={(updated) => {
            setCases((prev) => prev.map((c) => (c.case_id === updated.case_id ? updated : c)));
            setSelected(null);
          }}
        />
      )}
    </div>
  );
}
