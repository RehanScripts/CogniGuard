import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { EventRow } from "./EventTable";

const BAND_ORDER = ["low", "medium", "high", "very_high"];

interface BandDistributionProps {
  rows: EventRow[];
}

export default function BandDistribution({ rows }: BandDistributionProps) {
  const counts = BAND_ORDER.map((band) => ({
    band,
    count: rows.filter((r) => r.band === band).length,
  }));

  return (
    <div style={{ width: "100%", height: 200 }}>
      <ResponsiveContainer>
        <BarChart data={counts}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="band" />
          <YAxis allowDecimals={false} />
          <Tooltip />
          <Bar dataKey="count" fill="#2563eb" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
