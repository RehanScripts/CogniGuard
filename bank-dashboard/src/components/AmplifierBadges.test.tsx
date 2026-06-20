import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import AmplifierBadges from "./AmplifierBadges";

describe("AmplifierBadges", () => {
  it("renders a badge with the multiplier for each fired amplifier", () => {
    render(
      <AmplifierBadges amplifiers={[{ code: "NEW_BENEF_HIGHVAL", multiplier: 1.5, detail: "..." }]} />,
    );
    expect(screen.getByText(/NEW_BENEF_HIGHVAL/)).toBeInTheDocument();
    expect(screen.getByText(/×1\.5/)).toBeInTheDocument();
  });

  it("renders nothing when no amplifiers fired", () => {
    const { container } = render(<AmplifierBadges amplifiers={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
