import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { EmptyState } from "./EmptyState";

describe("EmptyState", () => {
  it("calls onAction from primary button", async () => {
    const onAction = vi.fn();
    const user = userEvent.setup();
    render(
      <EmptyState
        title="Nothing here"
        description="Add a source to get started."
        actionLabel="Add source"
        onAction={onAction}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Add source" }));
    expect(onAction).toHaveBeenCalled();
  });
});
