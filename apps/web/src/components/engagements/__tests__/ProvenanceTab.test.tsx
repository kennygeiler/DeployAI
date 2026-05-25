import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProvenanceTab } from "@/components/engagements/ProvenanceTab.client";

type FakeResponse = { ok: boolean; body: unknown; status?: number };

function mockFetchByUrl(handler: (url: string) => FakeResponse) {
  const calls: string[] = [];
  const fetchMock = vi.fn((url: string) => {
    calls.push(url);
    const r = handler(url);
    return Promise.resolve({
      ok: r.ok,
      status: r.status ?? (r.ok ? 200 : 500),
      json: () => Promise.resolve(r.body),
      text: () => Promise.resolve(""),
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

const ledgerEvents = {
  events: [
    {
      id: "ev-root",
      source_ref: "node-1",
      occurred_at: "2026-05-20T10:00:00Z",
    },
  ],
  next_cursor: null,
  source: "cp",
};

const chainBody = {
  rootEventId: "ev-root",
  nodes: [
    {
      id: "ev-root",
      occurredAt: "2026-05-20T10:00:00Z",
      sourceKind: "matrix_node_created",
      summary: "Decision created",
      actorKind: "user",
      depth: 0,
      truncated: false,
    },
  ],
  edges: [],
  truncatedAtDepth: null,
  truncatedNodeCount: null,
  source: "cp",
};

describe("ProvenanceTab", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the AI-generated draft label when a provenance narrative is present", async () => {
    mockFetchByUrl((url) => {
      if (url.includes("/ledger/chain/")) return { ok: true, body: chainBody };
      if (url.includes("/ledger?")) return { ok: true, body: ledgerEvents };
      if (url.includes("/insights")) {
        return {
          ok: true,
          body: {
            insights: [
              {
                id: "ins-1",
                insight_type: "decision_provenance_summary",
                body: "Why this decision exists, in one paragraph.",
                citation_node_ids: ["node-1"],
              },
            ],
          },
        };
      }
      return { ok: true, body: {} };
    });
    render(<ProvenanceTab engagementId="e1" nodeId="node-1" active={true} />);
    await waitFor(() => expect(screen.getByText(/AI-generated draft/i)).toBeTruthy());
    expect(screen.getByText(/Why this decision exists/)).toBeTruthy();
  });

  it("does not render the AI-generated draft label when no narrative is present", async () => {
    mockFetchByUrl((url) => {
      if (url.includes("/ledger/chain/")) return { ok: true, body: chainBody };
      if (url.includes("/ledger?")) return { ok: true, body: ledgerEvents };
      if (url.includes("/insights")) return { ok: true, body: { insights: [] } };
      return { ok: true, body: {} };
    });
    render(<ProvenanceTab engagementId="e1" nodeId="node-1" active={true} />);
    await waitFor(() => expect(screen.getByText(/Decision created/)).toBeTruthy());
    expect(screen.queryByText(/AI-generated draft/i)).toBeNull();
  });

  it("shows an empty state when no matrix-node ledger event matches the node id", async () => {
    mockFetchByUrl((url) => {
      if (url.includes("/ledger?")) {
        return { ok: true, body: { events: [], next_cursor: null, source: "cp" } };
      }
      return { ok: true, body: {} };
    });
    render(<ProvenanceTab engagementId="e1" nodeId="orphan-node" active={true} />);
    await waitFor(() =>
      expect(screen.getByText(/No ledger event found for this node yet/i)).toBeTruthy(),
    );
  });

  it("does not fetch when inactive", () => {
    const calls = mockFetchByUrl(() => ({ ok: true, body: {} }));
    render(<ProvenanceTab engagementId="e1" nodeId="node-1" active={false} />);
    expect(calls.length).toBe(0);
  });
});
