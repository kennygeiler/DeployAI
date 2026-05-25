import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  ProvenanceTree,
  type ProvenanceChain,
} from "@/components/engagements/ProvenanceTree.client";

function chain(): ProvenanceChain {
  return {
    rootEventId: "ev-root",
    nodes: [
      {
        id: "ev-root",
        occurredAt: "2026-05-20T10:00:00Z",
        sourceKind: "matrix_node_created",
        summary: "Decision: adopt pilot platform",
        actorKind: "user",
        depth: 0,
        truncated: false,
      },
      {
        id: "ev-mid",
        occurredAt: "2026-05-19T10:00:00Z",
        sourceKind: "llm_proposal_created",
        summary: "Proposal generated from extraction",
        actorKind: "system",
        depth: 1,
        truncated: false,
      },
      {
        id: "ev-leaf",
        occurredAt: "2026-05-18T10:00:00Z",
        sourceKind: "email_ingest",
        summary: "Customer email arrived",
        actorKind: "system",
        depth: 2,
        truncated: false,
      },
    ],
    edges: [
      { fromEventId: "ev-mid", toEventId: "ev-root" },
      { fromEventId: "ev-leaf", toEventId: "ev-mid" },
    ],
    truncatedAtDepth: null,
    truncatedNodeCount: null,
  };
}

describe("ProvenanceTree", () => {
  it("renders a 3-node chain with semantic list markup, root expanded by default", () => {
    render(<ProvenanceTree chain={chain()} />);
    expect(screen.getByText("Decision: adopt pilot platform")).toBeTruthy();
    expect(screen.getByText("Proposal generated from extraction")).toBeTruthy();
    expect(screen.getByText("Customer email arrived")).toBeTruthy();
    expect(screen.getByLabelText("Causal chain").tagName).toBe("UL");
    const lists = document.querySelectorAll("ul");
    expect(lists.length).toBeGreaterThanOrEqual(2);
    const listItems = document.querySelectorAll("li");
    expect(listItems.length).toBeGreaterThanOrEqual(3);
  });

  it("collapses and re-expands children when the toggle is clicked", async () => {
    const user = userEvent.setup();
    render(<ProvenanceTree chain={chain()} />);
    expect(screen.queryByText("Proposal generated from extraction")).toBeTruthy();
    const toggles = screen.getAllByRole("button", { name: /collapse upstream events/i });
    // The root node controls visibility of its direct children; click it.
    const rootToggle = toggles[0]!;
    await user.click(rootToggle);
    expect(screen.queryByText("Proposal generated from extraction")).toBeNull();
    const reExpand = screen.getByRole("button", { name: /expand upstream events/i });
    await user.click(reExpand);
    expect(screen.queryByText("Proposal generated from extraction")).toBeTruthy();
  });

  it("shows a truncation note when the chain was capped", () => {
    const c = chain();
    c.truncatedAtDepth = 3;
    c.truncatedNodeCount = 12;
    render(<ProvenanceTree chain={c} />);
    expect(
      screen.getByText(/Chain truncated at depth 3 \(12 additional events hidden\)/),
    ).toBeTruthy();
  });

  it("renders a fallback message when the root id is missing from nodes", () => {
    const c = chain();
    c.rootEventId = "missing";
    render(<ProvenanceTree chain={c} />);
    expect(screen.getByText(/No provenance chain available/i)).toBeTruthy();
  });
});
