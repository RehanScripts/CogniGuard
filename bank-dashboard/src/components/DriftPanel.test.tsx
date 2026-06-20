import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { DriftReportOut, ModelOut } from "../api";

const listModels = vi.fn();
const getDrift = vi.fn();
vi.mock("../api", () => ({ listModels: () => listModels(), getDrift: () => getDrift() }));

const MODELS: ModelOut[] = [
  {
    model_name: "xgboost_txn",
    versions: [
      {
        model_id: "m1",
        version: "v2",
        stage: "production",
        model_type: "xgboost",
        metrics: {},
        artifact_uri: "s3://bucket/key",
        deployed_at: "2026-06-20T05:00:00Z",
      },
    ],
  },
];

const DRIFT: DriftReportOut = {
  window: {
    live_start: "2026-06-19T05:00:00Z",
    live_end: "2026-06-20T05:00:00Z",
    reference_start: "2026-06-12T05:00:00Z",
    reference_end: "2026-06-19T05:00:00Z",
  },
  columns: {
    final_risk_score: { psi: 0.05, ks_stat: 0.1, ks_pvalue: 0.5, breached: false },
  },
  outcome: { n_resolved: 10, n_confirmed_fraud: 3, n_false_positive: 7, precision: 0.3 },
  breaches: [],
  retrained_models: [],
};

describe("DriftPanel", () => {
  it("renders model versions and drift columns once loaded", async () => {
    listModels.mockResolvedValue({ status: 200, body: MODELS });
    getDrift.mockResolvedValue({ status: 200, body: DRIFT });

    const DriftPanel = (await import("./DriftPanel")).default;
    render(<DriftPanel />);

    expect(await screen.findByText("xgboost_txn")).toBeInTheDocument();
    expect(await screen.findByText("final_risk_score")).toBeInTheDocument();
    expect(await screen.findByText("stable")).toBeInTheDocument();
  });

  it("shows an error state when loading fails", async () => {
    listModels.mockRejectedValue(new Error("network error"));
    getDrift.mockRejectedValue(new Error("network error"));

    const DriftPanel = (await import("./DriftPanel")).default;
    render(<DriftPanel />);

    expect(await screen.findByText(/failed to load/i)).toBeInTheDocument();
  });
});
