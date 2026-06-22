import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import Dashboard from "./Dashboard";

const { getProfileMock, listAccountsMock } = vi.hoisted(() => ({
  getProfileMock: vi.fn(),
  listAccountsMock: vi.fn(),
}));
vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    getSessionToken: () => "fake-token",
    getProfile: getProfileMock,
    listAccounts: listAccountsMock,
  };
});

describe("Dashboard", () => {
  it("renders the real account balance and profile name from the banking endpoints", async () => {
    getProfileMock.mockResolvedValue({
      status: 200,
      body: { full_name: "Genuine Customer", account_status: "ACTIVE" },
    });
    listAccountsMock.mockResolvedValue({
      status: 200,
      body: [
        {
          account_id: "a1",
          masked_account_number: "XXXXXX1234",
          account_type: "Savings",
          balance: 52340.5,
          currency: "INR",
        },
      ],
    });

    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Dashboard />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText(/welcome, genuine customer/i)).toBeInTheDocument());
    expect(screen.getByText(/52,340\.50/)).toBeInTheDocument();
    expect(screen.getByText(/XXXXXX1234/)).toBeInTheDocument();
  });

  it("shows an empty-accounts message when the customer has no accounts", async () => {
    getProfileMock.mockResolvedValue({ status: 200, body: { account_status: "ACTIVE" } });
    listAccountsMock.mockResolvedValue({ status: 200, body: [] });

    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Dashboard />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText(/no accounts found/i)).toBeInTheDocument());
  });
});
