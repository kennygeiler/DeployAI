import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MatrixNode, MatrixProposal } from "@/lib/bff/matrix-types";

import { MatrixProposals } from "./MatrixProposals.client";

function mkProposal(overrides: Partial<MatrixProposal>): MatrixProposal {
  return {
    id: "p1",
    engagement_id: "e1",
    source_event_id: "ev1",
    proposal_kind: "node",
    payload: { node_type: "system", title: "LiDAR ingest" },
    rationale: "Mentioned in the meeting notes.",
    status: "pending",
    created_at: "2026-05-09T00:00:00Z",
    decided_at: null,
    decided_by: null,
    result_node_id: null,
    result_edge_id: null,
    ...overrides,
  };
}

describe("MatrixProposals", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the empty-state message when there are no proposals", () => {
    render(<MatrixProposals engagementId="e1" proposals={[]} nodes={[]} onChanged={vi.fn()} />);
    expect(screen.getByText(/No proposals pending/)).toBeTruthy();
  });

  it("accepts a node proposal via the BFF and refreshes", async () => {
    const calls: Array<{ url: string; method: string }> = [];
    const fetchMock = vi.fn((url: string, init?: { method?: string }) => {
      calls.push({ url, method: init?.method ?? "GET" });
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ proposal: {} }) });
    });
    vi.stubGlobal("fetch", fetchMock);
    const onChanged = vi.fn();
    const user = userEvent.setup();

    render(
      <MatrixProposals
        engagementId="e1"
        proposals={[mkProposal({ payload: { node_type: "risk", title: "Calibration slip" } })]}
        nodes={[]}
        onChanged={onChanged}
      />,
    );

    // The summary line surfaces what's being proposed.
    expect(screen.getByText("risk: Calibration slip")).toBeTruthy();
    expect(screen.getByText("Mentioned in the meeting notes.")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Accept" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const posted = calls.find((c) => c.method === "POST")!;
    expect(posted.url).toContain("/api/bff/engagements/e1/proposals/p1/accept");
    expect(onChanged).toHaveBeenCalled();
  });

  it("renders an edge proposal as 'from —type→ to' using node titles", () => {
    const nodes: MatrixNode[] = [
      {
        id: "n1",
        engagement_id: "e1",
        node_type: "risk",
        title: "Calibration slip",
        identity_node_id: null,
        attributes: {},
        status: null,
        evidence_event_ids: [],
        created_at: "2026-05-09T00:00:00Z",
        updated_at: "2026-05-09T00:00:00Z",
      },
      {
        id: "n2",
        engagement_id: "e1",
        node_type: "system",
        title: "LiDAR ingest",
        identity_node_id: null,
        attributes: {},
        status: null,
        evidence_event_ids: [],
        created_at: "2026-05-09T00:00:00Z",
        updated_at: "2026-05-09T00:00:00Z",
      },
    ];
    render(
      <MatrixProposals
        engagementId="e1"
        proposals={[
          mkProposal({
            id: "p2",
            proposal_kind: "edge",
            payload: {
              edge_type: "threatens",
              from_node_id: "n1",
              to_node_id: "n2",
            },
            rationale: null,
          }),
        ]}
        nodes={nodes}
        onChanged={vi.fn()}
      />,
    );
    expect(screen.getByText("Calibration slip —threatens→ LiDAR ingest")).toBeTruthy();
  });
});
