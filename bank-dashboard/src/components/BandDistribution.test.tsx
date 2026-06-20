import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { EventRow } from "./EventTable";
import BandDistribution from "./BandDistribution";

// Recharts is test-fragile in jsdom (zero layout dimensions) -- a smoke-test render
// is the right bar here, not pixel/visual assertions.
const ROWS: EventRow[] = [
  { key: "1", entityType: "login", band: "low", score: 5, action: "allow", ts: "2026-06-20T05:00:00Z" },
  { key: "2", entityType: "login", band: "low", score: 5, action: "allow", ts: "2026-06-20T05:00:01Z" },
  {
    key: "3",
    entityType: "transaction",
    band: "high",
    score: 70,
    action: "verify",
    ts: "2026-06-20T05:01:00Z",
  },
];

describe("BandDistribution", () => {
  it("renders without throwing given a mix of bands", () => {
    expect(() => render(<BandDistribution rows={ROWS} />)).not.toThrow();
  });

  it("renders without throwing given no rows", () => {
    expect(() => render(<BandDistribution rows={[]} />)).not.toThrow();
  });
});
