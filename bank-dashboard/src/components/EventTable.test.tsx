import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import EventTable, { type EventRow } from "./EventTable";

const ROWS: EventRow[] = [
  {
    key: "1",
    entityType: "login",
    entityId: "abcdef1234567890",
    band: "low",
    score: 5,
    action: "allow",
    ts: "2026-06-20T05:00:00Z",
  },
  {
    key: "2",
    entityType: "transaction",
    entityId: "deadbeef00001111",
    band: "high",
    score: 70,
    action: "verify",
    ts: "2026-06-20T05:01:00Z",
  },
];

describe("EventTable", () => {
  it("renders a row per event with band/score/action", () => {
    render(<EventTable rows={ROWS} />);
    expect(screen.getByText("low")).toBeInTheDocument();
    expect(screen.getByText("high")).toBeInTheDocument();
    expect(screen.getByText("allow")).toBeInTheDocument();
    expect(screen.getByText("verify")).toBeInTheDocument();
  });

  it("renders an empty state with no rows", () => {
    render(<EventTable rows={[]} />);
    expect(screen.getByText(/no events yet/i)).toBeInTheDocument();
  });
});
