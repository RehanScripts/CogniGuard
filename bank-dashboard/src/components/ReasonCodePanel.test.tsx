import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ReasonCodePanel from "./ReasonCodePanel";

describe("ReasonCodePanel", () => {
  it("renders code/detail/sigma for each reason code", () => {
    render(
      <ReasonCodePanel
        reasonCodes={[
          { code: "IMPOSSIBLE_TRAVEL", detail: "Login from a location...", sigma: 3.2 },
        ]}
      />,
    );
    expect(screen.getByText("IMPOSSIBLE_TRAVEL")).toBeInTheDocument();
    expect(screen.getByText(/Login from a location/i)).toBeInTheDocument();
    expect(screen.getByText(/σ=3\.20/)).toBeInTheDocument();
  });

  it("renders an empty state with no reason codes", () => {
    render(<ReasonCodePanel reasonCodes={[]} />);
    expect(screen.getByText(/no reason codes/i)).toBeInTheDocument();
  });
});
