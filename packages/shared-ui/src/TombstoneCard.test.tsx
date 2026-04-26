import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TombstoneCard } from "./TombstoneCard";

describe("TombstoneCard", () => {
  it("renders retention metadata and node id", () => {
    render(
      <TombstoneCard
        retentionReason="90-day rolling retention (policy T-1)."
        destroyedAt="2026-01-10T12:00:00Z"
        originalNodeId="a1b2c3d4-aaaa-bbbb-cccc-ddddeeee0001"
        authorityActor="security@example.gov"
      />,
    );
    expect(screen.getByRole("article")).toBeInTheDocument();
    expect(screen.getByText(/90-day rolling retention/)).toBeInTheDocument();
    expect(screen.getByText("a1b2c3d4-aaaa-bbbb-cccc-ddddeeee0001")).toBeInTheDocument();
  });

  it("shows appeal when enabled", async () => {
    const onAppeal = vi.fn();
    const user = userEvent.setup();
    render(
      <TombstoneCard
        retentionReason="Removed."
        destroyedAt="2026-01-10T12:00:00Z"
        originalNodeId="n1"
        authorityActor="admin"
        appealAvailable
        onAppeal={onAppeal}
      />,
    );
    await user.click(screen.getByRole("button", { name: /Request review/ }));
    expect(onAppeal).toHaveBeenCalled();
  });
});
