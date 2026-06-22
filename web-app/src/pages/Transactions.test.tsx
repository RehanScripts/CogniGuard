import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import Transactions from "./Transactions";

const { listTransactionsMock, listBeneficiariesMock } = vi.hoisted(() => ({
  listTransactionsMock: vi.fn(),
  listBeneficiariesMock: vi.fn(),
}));
vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    getSessionToken: () => "fake-token",
    listTransactions: listTransactionsMock,
    listBeneficiaries: listBeneficiariesMock,
  };
});

describe("Transactions", () => {
  it("renders transaction history and beneficiaries from the banking endpoints", async () => {
    listTransactionsMock.mockResolvedValue({
      status: 200,
      body: [
        {
          transaction_id: "t1",
          beneficiary_name: "Acme Traders",
          masked_beneficiary_account: "XXXX5678",
          amount: 2500,
          currency: "INR",
          transfer_type: "UPI",
          status: "SUCCESS",
          initiated_at: "2026-06-20T10:00:00Z",
        },
      ],
    });
    listBeneficiariesMock.mockResolvedValue({
      status: 200,
      body: [
        {
          beneficiary_id: "b1",
          name: "Acme Traders",
          masked_account_number: "XXXX5678",
          is_verified: true,
          transfer_count: 3,
        },
      ],
    });

    render(
      <MemoryRouter initialEntries={["/transactions"]}>
        <Transactions />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText("Acme Traders")).toBeInTheDocument());
    expect(screen.getByText(/2,500\.00/)).toBeInTheDocument();
    expect(screen.getByText(/verified/i)).toBeInTheDocument();
  });

  it("shows empty-state messages when there is no history", async () => {
    listTransactionsMock.mockResolvedValue({ status: 200, body: [] });
    listBeneficiariesMock.mockResolvedValue({ status: 200, body: [] });

    render(
      <MemoryRouter initialEntries={["/transactions"]}>
        <Transactions />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText(/no transactions yet/i)).toBeInTheDocument());
    expect(screen.getByText(/no saved beneficiaries/i)).toBeInTheDocument();
  });
});
