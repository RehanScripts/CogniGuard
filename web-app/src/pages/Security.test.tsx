import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import Security from "./Security";

const { getSecuritySettingsMock } = vi.hoisted(() => ({ getSecuritySettingsMock: vi.fn() }));
vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    getSessionToken: () => "fake-token",
    getSecuritySettings: getSecuritySettingsMock,
  };
});

describe("Security", () => {
  it("renders trusted devices and active sessions from the banking endpoint", async () => {
    getSecuritySettingsMock.mockResolvedValue({
      status: 200,
      body: {
        trusted_devices: [{ device_id: "d1", label: "Pixel 8", is_trusted: true }],
        active_sessions: [{ session_id: "s1", device_label: "Chrome on Windows", location: "Mumbai, IN" }],
      },
    });

    render(
      <MemoryRouter initialEntries={["/security"]}>
        <Security />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText("Pixel 8")).toBeInTheDocument());
    expect(screen.getByText("Trusted")).toBeInTheDocument();
    expect(screen.getByText("Chrome on Windows")).toBeInTheDocument();
    expect(screen.getByText("Mumbai, IN")).toBeInTheDocument();
  });

  it("shows empty-state messages when there is nothing to show", async () => {
    getSecuritySettingsMock.mockResolvedValue({
      status: 200,
      body: { trusted_devices: [], active_sessions: [] },
    });

    render(
      <MemoryRouter initialEntries={["/security"]}>
        <Security />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText(/no trusted devices/i)).toBeInTheDocument());
    expect(screen.getByText(/no active sessions/i)).toBeInTheDocument();
  });
});
