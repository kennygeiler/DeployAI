import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { OverrideComposer } from "./OverrideComposer";

const opts = [
  { id: "a", label: "Node A" },
  { id: "b", label: "Node B" },
];

afterEach(cleanup);

describe("OverrideComposer", () => {
  it("validates and calls onSubmit with payload", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<OverrideComposer evidenceOptions={opts} onSubmit={onSubmit} />);
    await user.click(screen.getByRole("button", { name: /submit override/i }));
    expect(
      await screen.findByText(/3 fields need attention/i),
    ).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();

    await user.type(screen.getByRole("textbox", { name: /what changed/i }), "Updated owner");
    await user.type(screen.getByRole("textbox", { name: /justification/i }), "Policy change");
    await user.click(screen.getByLabelText("Node A"));
    await user.click(screen.getByRole("button", { name: /submit override/i }));
    expect(onSubmit).toHaveBeenCalledWith({
      whatChanged: "Updated owner",
      why: "Policy change",
      evidenceNodeIds: ["a"],
    });
  });
});
