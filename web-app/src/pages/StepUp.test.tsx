import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import StepUp from "./StepUp";

function renderWithChallenge(challengeType: string) {
  return render(
    <MemoryRouter
      initialEntries={[
        {
          pathname: "/step-up",
          state: {
            challenge: { challenge_type: challengeType, assurance: "light", challenge_id: "c1" },
            requiredFactors: [challengeType],
            username: "genuine",
          },
        },
      ]}
    >
      <StepUp />
    </MemoryRouter>,
  );
}

describe("StepUp", () => {
  it("renders a text input for OTP", () => {
    renderWithChallenge("OTP");
    expect(screen.getByPlaceholderText("123456")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /simulate/i })).not.toBeInTheDocument();
  });

  it("renders a text input for MPIN", () => {
    renderWithChallenge("MPIN");
    expect(screen.getByPlaceholderText("123456")).toBeInTheDocument();
  });

  it("renders a simulate button for FINGERPRINT, not a text input", () => {
    renderWithChallenge("FINGERPRINT");
    expect(screen.queryByPlaceholderText("123456")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /simulate fingerprint/i })).toBeInTheDocument();
  });
});
