import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface LatencyHistogramProps {
  latenciesMs: number[];
  budgetMs: number;
}

const BUCKET_SIZE_MS = 50;

// Real data from EventOut.latency_ms (already returned by GET /admin/events) -- not a
// Phase 12 placeholder, unlike DriftPanel/the challenger-shadow view.
export default function LatencyHistogram({ latenciesMs, budgetMs }: LatencyHistogramProps) {
  if (latenciesMs.length === 0) {
    return <p className="text-sm text-soc-muted">No latency data yet.</p>;
  }

  const buckets = new Map<number, number>();
  for (const ms of latenciesMs) {
    const bucket = Math.floor(ms / BUCKET_SIZE_MS) * BUCKET_SIZE_MS;
    buckets.set(bucket, (buckets.get(bucket) ?? 0) + 1);
  }
  const data = Array.from(buckets.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([bucket, count]) => ({ bucket: `${bucket}ms`, count, raw: bucket }));

  const overBudget = latenciesMs.filter((ms) => ms > budgetMs).length;

  return (
    <div>
      <div style={{ width: "100%", height: 200 }}>
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -16 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
            <XAxis dataKey="bucket" tick={{ fontSize: 10, fill: "#64748B" }} />
            <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: "#64748B" }} />
            <Tooltip
              contentStyle={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 8, fontSize: 11 }}
              cursor={{ fill: "#F2F5F8" }}
            />
            <Bar dataKey="count" radius={[3, 3, 0, 0]}>
              {data.map((entry) => (
                <Cell key={entry.bucket} fill={entry.raw > budgetMs ? "#DC2626" : "#176FC1"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-2 text-xs text-soc-muted">
        Budget: {budgetMs} ms ·{" "}
        <span className={overBudget > 0 ? "font-semibold text-soc-danger" : "text-soc-success"}>
          {overBudget} of {latenciesMs.length} event{latenciesMs.length !== 1 ? "s" : ""} over budget
        </span>
      </p>
    </div>
  );
}
