import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LedgerDiffView } from "@/components/engagements/LedgerDiffView.client";

afterEach(() => {
  vi.unstubAllGlobals();
});

function mockFetch(handler: (url: string) => { ok: boolean; body: unknown; status?: number }) {
  const fetchMock = vi.fn((url: string) => {
    const r = handler(url);
    return Promise.resolve({
      ok: r.ok,
      status: r.status ?? (r.ok ? 200 : 404),
      json: () => Promise.resolve(r.body),
      text: () => Promise.resolve(""),
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("LedgerDiffView", () => {
  it("renders nothing when the matrix-snapshot endpoint 404s", async () => {
    const fetchMock = mockFetch(() => ({ ok: false, body: { error: "none" } }));

    const { container } = render(
      <LedgerDiffView
        engagementId="eng-1"
        nodeId="node-1"
        occurredAt="2026-05-22T10:00:00Z"
        currentNodeFields={{ title: "New", node_type: "risk", attributes: {} }}
      />,
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await waitFor(() =>
      expect(container.querySelector("[data-testid='ledger-diff-view']")).toBeNull(),
    );
  });

  it("renders nothing when the prior snapshot has no matching node", async () => {
    mockFetch(() => ({
      ok: true,
      body: {
        snapshot: {
          captured_at: "2026-05-21T00:00:00Z",
          nodes: [{ id: "other-node", title: "x", node_type: "risk", attributes: {} }],
          edges: [],
        },
        source: "cp",
      },
    }));

    const { container } = render(
      <LedgerDiffView
        engagementId="eng-1"
        nodeId="node-1"
        occurredAt="2026-05-22T10:00:00Z"
        currentNodeFields={{ title: "New", node_type: "risk", attributes: {} }}
      />,
    );

    await waitFor(() =>
      expect(container.querySelector("[data-testid='ledger-diff-view']")).toBeNull(),
    );
  });

  it("renders the changed fields when a prior node snapshot differs", async () => {
    mockFetch(() => ({
      ok: true,
      body: {
        snapshot: {
          captured_at: "2026-05-21T00:00:00Z",
          nodes: [
            {
              id: "node-1",
              title: "Old title",
              node_type: "risk",
              attributes: { severity: "low" },
            },
          ],
          edges: [],
        },
        source: "cp",
      },
    }));

    render(
      <LedgerDiffView
        engagementId="eng-1"
        nodeId="node-1"
        occurredAt="2026-05-22T10:00:00Z"
        currentNodeFields={{
          title: "New title",
          node_type: "risk",
          attributes: { severity: "high" },
        }}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("ledger-diff-view")).toBeTruthy();
    });
    const rendered = screen.getByTestId("ledger-diff-view");
    expect(rendered.textContent).toContain("title");
    expect(rendered.textContent).toContain("Old title");
    expect(rendered.textContent).toContain("New title");
    expect(rendered.textContent).toContain("attributes");
  });
});
