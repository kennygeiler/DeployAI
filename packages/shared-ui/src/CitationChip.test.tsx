import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CitationChip } from "./CitationChip";

const preview = {
  citationId: "b3d4e5f6-1111-2222-3333-444455556666",
  retrievalPhase: "P4 Production",
  confidence: "0.94",
  signedTimestamp: "2026-04-23T14:00:00Z",
} as const;

function noop() {}

describe("CitationChip", () => {
  it("toggles aria-expanded and calls onToggleExpand on activation", async () => {
    const onToggle = vi.fn();
    const user = userEvent.setup();

    const { rerender } = render(
      <CitationChip
        label="07:11 DOT standup"
        expanded={false}
        onToggleExpand={onToggle}
        onViewEvidence={noop}
        onOverride={noop}
        onCopyLink={noop}
        onCiteInOverride={noop}
        preview={preview}
      />,
    );

    const btn = screen.getByRole("button", { name: /07:11 DOT standup/ });
    expect(btn).toHaveAttribute("aria-expanded", "false");

    await user.click(btn);
    expect(onToggle).toHaveBeenCalledTimes(1);

    rerender(
      <CitationChip
        label="07:11 DOT standup"
        expanded
        onToggleExpand={onToggle}
        onViewEvidence={noop}
        onOverride={noop}
        onCopyLink={noop}
        onCiteInOverride={noop}
        preview={preview}
      />,
    );
    expect(btn).toHaveAttribute("aria-expanded", "true");
  });

  it("does not call onToggleExpand when disableExpand and aria-disabled", async () => {
    const onToggle = vi.fn();
    const user = userEvent.setup();
    render(
      <CitationChip
        label="Read-only"
        expanded={false}
        disableExpand
        onToggleExpand={onToggle}
        onViewEvidence={noop}
        onOverride={noop}
        onCopyLink={noop}
        onCiteInOverride={noop}
        preview={preview}
      />,
    );
    const btn = screen.getByRole("button", { name: /Read-only/ });
    expect(btn).toHaveAttribute("aria-disabled", "true");
    await user.click(btn);
    expect(onToggle).not.toHaveBeenCalled();
  });

  it("shows trust earn-back label when trustRecoveryVisible", () => {
    render(
      <CitationChip
        label="Cue"
        expanded={false}
        onToggleExpand={noop}
        onViewEvidence={noop}
        onOverride={noop}
        onCopyLink={noop}
        onCiteInOverride={noop}
        preview={preview}
        trustRecoveryVisible
      />,
    );
    expect(screen.getByText("Recovered")).toHaveAttribute("data-trust-earn-back", "true");
  });

  it("renders override badge as link when overrideEvidenceHref is set", () => {
    render(
      <CitationChip
        label="Ov"
        expanded={false}
        visualState="overridden"
        onToggleExpand={noop}
        onViewEvidence={noop}
        onOverride={noop}
        onCopyLink={noop}
        onCiteInOverride={noop}
        preview={preview}
        overrideEvidenceHref="/evidence/test-node"
      />,
    );
    const link = screen.getByRole("link", { name: /view override evidence/i });
    expect(link).toHaveAttribute("href", "/evidence/test-node");
  });
});
