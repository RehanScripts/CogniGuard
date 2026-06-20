import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ChannelSwitcher from "./ChannelSwitcher";

describe("ChannelSwitcher", () => {
  it("toggles its own local state and calls onChange -- no SDK side effect", () => {
    const onChange = vi.fn();
    render(<ChannelSwitcher onChange={onChange} />);

    const mobileButton = screen.getByRole("button", { name: "Mobile" });
    fireEvent.click(mobileButton);

    expect(onChange).toHaveBeenCalledWith("mobile");
    expect(mobileButton.className).toContain("bg-blue-600");
  });
});
