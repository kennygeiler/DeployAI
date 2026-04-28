import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { TwoPartyConsentDialog } from "./TwoPartyConsentDialog";

describe("TwoPartyConsentDialog", () => {
  it("requires confirmation before accept is enabled", async () => {
    const user = userEvent.setup();
    const onAccept = vi.fn();
    const onDecline = vi.fn();
    render(<TwoPartyConsentDialog open onAccept={onAccept} onDecline={onDecline} />);

    const accept = screen.getByRole("button", { name: /accept and continue/i });
    expect(accept).toBeDisabled();

    await user.click(screen.getByRole("checkbox"));
    expect(accept).toBeEnabled();

    await user.click(accept);
    expect(onAccept).toHaveBeenCalledWith("US-default");
    expect(onDecline).not.toHaveBeenCalled();
  });

  it("invokes onDecline", async () => {
    const user = userEvent.setup();
    const onAccept = vi.fn();
    const onDecline = vi.fn();
    render(<TwoPartyConsentDialog open onAccept={onAccept} onDecline={onDecline} />);

    await user.click(screen.getByRole("button", { name: /decline/i }));
    expect(onDecline).toHaveBeenCalled();
    expect(onAccept).not.toHaveBeenCalled();
  });
});
