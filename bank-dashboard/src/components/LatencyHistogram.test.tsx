import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import LatencyHistogram from "./LatencyHistogram";

describe("LatencyHistogram", () => {
  it("renders without throwing given latency values", () => {
    expect(() =>
      render(<LatencyHistogram latenciesMs={[120, 180, 310, 90]} budgetMs={300} />),
    ).not.toThrow();
  });

  it("renders an empty state with no data", () => {
    render(<LatencyHistogram latenciesMs={[]} budgetMs={300} />);
    expect(screen.getByText(/no latency data yet/i)).toBeInTheDocument();
  });

  it("reports how many events are over budget", () => {
    render(<LatencyHistogram latenciesMs={[100, 400]} budgetMs={300} />);
    expect(screen.getByText(/1 of 2 event/i)).toBeInTheDocument();
  });
});
