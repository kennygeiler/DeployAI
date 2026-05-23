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

  it("accepts a single node proposal via the BFF and refreshes", async () => {
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

    expect(screen.getByText("risk: Calibration slip")).toBeTruthy();
    // Single proposal in group → group-level button reads "Accept" (no dedup tag).
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

  // --- Polish.1 — dedup grouping + filter + bulk actions ------------------

  it("groups duplicate proposals by (kind, summary) and shows the count", () => {
    const proposals = [
      mkProposal({
        id: "p1",
        source_event_id: "ev1",
        payload: { node_type: "stakeholder", title: "Dana Carter" },
      }),
      mkProposal({
        id: "p2",
        source_event_id: "ev2",
        payload: { node_type: "stakeholder", title: "Dana Carter" },
      }),
      mkProposal({
        id: "p3",
        source_event_id: "ev3",
        payload: { node_type: "stakeholder", title: "Dana Carter" },
      }),
    ];
    render(
      <MatrixProposals engagementId="e1" proposals={proposals} nodes={[]} onChanged={vi.fn()} />,
    );
    // The group renders once, with a ×3 multiplicity badge.
    const labels = screen.getAllByText("stakeholder: Dana Carter");
    expect(labels.length).toBe(1);
    expect(screen.getByText("×3")).toBeTruthy();
    // Header shows totals: 3 of 3 proposals, 1 unique group.
    expect(screen.getByText(/3 of 3 proposal\(s\) — 1 unique/)).toBeTruthy();
  });

  it("group-Accept on duplicates accepts the first and rejects the rest", async () => {
    const calls: Array<{ url: string; method: string }> = [];
    const fetchMock = vi.fn((url: string, init?: { method?: string }) => {
      calls.push({ url, method: init?.method ?? "GET" });
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ proposal: {} }) });
    });
    vi.stubGlobal("fetch", fetchMock);
    const onChanged = vi.fn();
    const user = userEvent.setup();

    const proposals = [
      mkProposal({
        id: "p1",
        source_event_id: "ev1",
        payload: { node_type: "stakeholder", title: "Dana Carter" },
      }),
      mkProposal({
        id: "p2",
        source_event_id: "ev2",
        payload: { node_type: "stakeholder", title: "Dana Carter" },
      }),
    ];
    render(
      <MatrixProposals engagementId="e1" proposals={proposals} nodes={[]} onChanged={onChanged} />,
    );
    // With 2 proposals the group-Accept button is labelled "Accept (dedup)".
    await user.click(screen.getByRole("button", { name: "Accept (dedup)" }));
    await waitFor(() => expect(calls.filter((c) => c.method === "POST").length).toBe(2));
    const posts = calls.filter((c) => c.method === "POST");
    // First proposal gets accepted, the rest get rejected as dupes.
    expect(posts[0]?.url).toContain("/proposals/p1/accept");
    expect(posts[1]?.url).toContain("/proposals/p2/reject");
    expect(onChanged).toHaveBeenCalled();
  });

  it("kind filter narrows the list to nodes or edges", async () => {
    const nodes: MatrixNode[] = [
      {
        id: "n1",
        engagement_id: "e1",
        node_type: "stakeholder",
        title: "Dana",
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
        title: "LiDAR",
        identity_node_id: null,
        attributes: {},
        status: null,
        evidence_event_ids: [],
        created_at: "2026-05-09T00:00:00Z",
        updated_at: "2026-05-09T00:00:00Z",
      },
    ];
    const proposals = [
      mkProposal({
        id: "p1",
        proposal_kind: "node",
        payload: { node_type: "stakeholder", title: "Marcus" },
      }),
      mkProposal({
        id: "p2",
        proposal_kind: "edge",
        payload: {
          edge_type: "sponsors",
          from_node_id: "n1",
          to_node_id: "n2",
        },
      }),
    ];
    const user = userEvent.setup();
    render(
      <MatrixProposals engagementId="e1" proposals={proposals} nodes={nodes} onChanged={vi.fn()} />,
    );
    // All visible by default.
    expect(screen.getByText("stakeholder: Marcus")).toBeTruthy();
    expect(screen.getByText("Dana —sponsors→ LiDAR")).toBeTruthy();

    // Filter to edges only — node group disappears.
    await user.selectOptions(screen.getByLabelText("Kind"), "edge");
    expect(screen.queryByText("stakeholder: Marcus")).toBeNull();
    expect(screen.getByText("Dana —sponsors→ LiDAR")).toBeTruthy();
  });

  it("expanding a group reveals each underlying proposal with its rationale", async () => {
    const user = userEvent.setup();
    render(
      <MatrixProposals
        engagementId="e1"
        proposals={[
          mkProposal({
            id: "p1",
            source_event_id: "abc12345-0000-0000-0000-000000000000",
            rationale: "Mentioned in the kickoff notes.",
            payload: { node_type: "stakeholder", title: "Dana Carter" },
          }),
        ]}
        nodes={[]}
        onChanged={vi.fn()}
      />,
    );
    // Rationale is hidden until the group is expanded.
    expect(screen.queryByText("Mentioned in the kickoff notes.")).toBeNull();
    await user.click(screen.getByRole("button", { name: /stakeholder: Dana Carter/ }));
    expect(screen.getByText("Mentioned in the kickoff notes.")).toBeTruthy();
    // Source-event-id prefix is also surfaced for traceability.
    expect(screen.getByText(/src: abc12345/)).toBeTruthy();
  });
});
