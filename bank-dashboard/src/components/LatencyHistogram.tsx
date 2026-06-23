import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface LatencyHistogramProps {
  latenciesMs: number[];
  budgetMs: number;
}

const BUCKET_SIZE_MS = 50;

// Real data from EventOut.latency_ms (already returned by GET /admin/events) -- not a
// Phase 12 placeholder, unlike DriftPanel/the challenger-shadow view.
export default function LatencyHistogram({ latenciesMs, budgetMs }: LatencyHistogramProps) {
  if (latenciesMs.length === 0) {
    return <p className="text-sm text-gray-400">No latency data yet.</p>;
  }

  const buckets = new Map<number, number>();
  for (const ms of latenciesMs) {
    const bucket = Math.floor(ms / BUCKET_SIZE_MS) * BUCKET_SIZE_MS;
    buckets.set(bucket, (buckets.get(bucket) ?? 0) + 1);
  }
  const data = Array.from(buckets.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([bucket, count]) => ({ bucket: `${bucket}ms`, count }));

  const overBudget = latenciesMs.filter((ms) => ms > budgetMs).length;

  return (
    <div>
      <div style={{ width: "100%", height: 200 }}>
        <ResponsiveContainer>
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="bucket" />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Bar dataKey="count" fill="#125A9C" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-1 text-xs text-gray-500">
        Budget: {budgetMs}ms · {overBudget} of {latenciesMs.length} event(s) over budget
      </p>
    </div>
  );
}
