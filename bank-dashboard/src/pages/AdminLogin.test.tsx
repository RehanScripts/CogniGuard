import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import AdminLogin from "./AdminLogin";

const { adminLoginMock, setAdminTokenMock } = vi.hoisted(() => ({
  adminLoginMock: vi.fn(),
  setAdminTokenMock: vi.fn(),
}));
vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return { ...actual, adminLogin: adminLoginMock, setAdminToken: setAdminTokenMock };
});

function renderAdminLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <Routes>
        <Route path="/login" element={<AdminLogin />} />
        <Route path="/" element={<div data-testid="live-page" />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("AdminLogin", () => {
  it("renders the email/password form", () => {
    renderAdminLogin();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
  });

  it("stores the token and navigates to the live feed on success", async () => {
    adminLoginMock.mockResolvedValue({
      status: 200,
      body: { token: "tok", analyst_id: "a1", role: "admin" },
    });
    renderAdminLogin();
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(screen.getByTestId("live-page")).toBeInTheDocument());
    expect(setAdminTokenMock).toHaveBeenCalledWith("tok");
  });

  it("shows an error message on invalid credentials", async () => {
    adminLoginMock.mockResolvedValue({ status: 401, body: {} });
    renderAdminLogin();
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(screen.getByText(/invalid email or password/i)).toBeInTheDocument());
  });
});
