import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { EventRow } from "./EventTable";

const BAND_ORDER = ["low", "medium", "high", "very_high"];

const BAND_COLORS: Record<string, string> = {
  low: "#15803D",
  medium: "#B45309",
  high: "#DC2626",
  very_high: "#9F1239",
};

const BAND_LABELS: Record<string, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
  very_high: "Critical",
};

export default function BandDistribution({ rows }: { rows: EventRow[] }) {
  const counts = BAND_ORDER.map((band) => ({
    band: BAND_LABELS[band] ?? band,
    bandKey: band,
    count: rows.filter((r) => r.band === band).length,
  }));

  return (
    <div style={{ width: "100%", height: 180 }}>
      <ResponsiveContainer>
        <BarChart data={counts} barSize={28}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
          <XAxis
            dataKey="band"
            tick={{ fontSize: 11, fill: "#64748B", fontWeight: 600 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            allowDecimals={false}
            tick={{ fontSize: 11, fill: "#64748B" }}
            axisLine={false}
            tickLine={false}
            width={28}
          />
          <Tooltip
            contentStyle={{ background: "#fff", border: "1px solid #E2E8F0", borderRadius: 8, fontSize: 12 }}
            cursor={{ fill: "#F2F5F8" }}
          />
          <Bar dataKey="count" radius={[4, 4, 0, 0]}>
            {counts.map((entry) => (
              <Cell key={entry.bandKey} fill={BAND_COLORS[entry.bandKey] ?? "#176FC1"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
