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
  it("renders a 6-box OTP grid for OTP", () => {
    renderWithChallenge("OTP");
    expect(screen.getByText(/demo otp code is/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^verify$/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /simulate/i })).not.toBeInTheDocument();
  });

  it("renders a 6-box OTP grid for MPIN", () => {
    renderWithChallenge("MPIN");
    expect(screen.getByText(/demo otp code is/i)).toBeInTheDocument();
  });

  it("renders a simulate button for FINGERPRINT, not an OTP grid", () => {
    renderWithChallenge("FINGERPRINT");
    expect(screen.queryByText(/demo otp code is/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /simulate fingerprint/i })).toBeInTheDocument();
  });
});
