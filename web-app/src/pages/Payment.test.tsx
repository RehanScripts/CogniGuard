import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import Payment from "./Payment";

vi.mock("@cogniguard/behavior-sdk", () => ({
  CogniGuard: { collect: vi.fn().mockResolvedValue({}) },
}));

const { scorePaymentMock } = vi.hoisted(() => ({ scorePaymentMock: vi.fn() }));
vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    getSessionToken: () => "fake-token",
    scorePayment: scorePaymentMock,
  };
});

function fillAndSubmit() {
  fireEvent.change(screen.getByLabelText(/beneficiary vpa/i), { target: { value: "payee@upi" } });
  fireEvent.change(screen.getByLabelText(/amount/i), { target: { value: "5000" } });
  fireEvent.click(screen.getByRole("button", { name: /send/i }));
}

describe("Payment", () => {
  it("renders CoercionCheck first, then ManualAmountEntry, then CoolingNotice when txn_controls flags all three", async () => {
    scorePaymentMock.mockResolvedValue({
      status: 200,
      body: {
        action: "verify",
        risk_band: "high",
        risk_score: 70,
        txn_controls: {
          coercion_check: true,
          manual_amount: true,
          cooling_until: "2026-06-20T06:00:00Z",
          reconfirm: null,
        },
      },
    });
    render(<MemoryRouter><Payment /></MemoryRouter>);
    fillAndSubmit();

    await waitFor(() => expect(screen.getByText(/is someone instructing you/i)).toBeInTheDocument());
    expect(screen.queryByText(/re-type the amount/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /no, this is genuinely me/i }));
    await waitFor(() => expect(screen.getByText(/re-type the amount/i)).toBeInTheDocument());
  });

  it("renders none of the controls when txn_controls is null", async () => {
    scorePaymentMock.mockResolvedValue({
      status: 200,
      body: { action: "allow", risk_band: "low", risk_score: 5, txn_controls: null },
    });
    render(<MemoryRouter><Payment /></MemoryRouter>);
    fillAndSubmit();

    await waitFor(() => expect(screen.getByText(/standard verification/i)).toBeInTheDocument());
    expect(screen.queryByText(/is someone instructing you/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/re-type the amount/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/cooling period/i)).not.toBeInTheDocument();
  });
});
