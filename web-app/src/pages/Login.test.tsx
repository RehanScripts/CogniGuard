import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import Login from "./Login";

vi.mock("@cogniguard/behavior-sdk", () => ({
  CogniGuard: {
    init: vi.fn(),
    attach: vi.fn(),
    detach: vi.fn(),
    collect: vi.fn().mockResolvedValue({}),
  },
}));

const { loginMock } = vi.hoisted(() => ({ loginMock: vi.fn() }));
vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return { ...actual, login: loginMock, setSessionToken: vi.fn() };
});

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/step-up" element={<div data-testid="step-up-page" />} />
        <Route path="/dashboard" element={<div data-testid="dashboard-page" />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Login", () => {
  it("renders the username/password form", () => {
    renderLogin();
    expect(screen.getByLabelText(/username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
  });

  it("navigates to the dashboard on allow", async () => {
    loginMock.mockResolvedValue({
      status: 200,
      body: { action: "allow", session_token: "tok" },
    });
    renderLogin();
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(screen.getByTestId("dashboard-page")).toBeInTheDocument());
  });

  it("routes to step-up with the challenge on verify", async () => {
    loginMock.mockResolvedValue({
      status: 200,
      body: {
        action: "verify",
        step_up: { challenge_type: "OTP", assurance: "light", challenge_id: "c1" },
        required_factors: ["OTP"],
      },
    });
    renderLogin();
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(screen.getByTestId("step-up-page")).toBeInTheDocument());
  });
});
