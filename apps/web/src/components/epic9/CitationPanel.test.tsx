import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CitationPanel } from "./CitationPanel.client";

type CitationEvent = {
  id: string;
  occurred_at: string;
  event_type: string;
  source_ref: string | null;
  summary: string;
};

function mkEvent(overrides: Partial<CitationEvent> = {}): CitationEvent {
  return {
    id: "ev1",
    occurred_at: "2026-05-09T10:00:00Z",
    event_type: "ingest.email",
    source_ref: "https://example/em/1",
    summary: "Stakeholder confirmed the pilot date",
    ...overrides,
  };
}

function mockFetch(handler: () => { ok: boolean; body: unknown; text?: string }) {
  const calls: string[] = [];
  const fetchMock = vi.fn((url: string) => {
    calls.push(url);
    const r = handler();
    return Promise.resolve({
      ok: r.ok,
      status: r.ok ? 200 : 500,
      json: () => Promise.resolve(r.body),
      text: () => Promise.resolve(r.text ?? ""),
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

describe("CitationPanel", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("opens with ids, fetches events, and renders them", async () => {
    const events = [
      mkEvent({ id: "ev1", summary: "First cited event" }),
      mkEvent({
        id: "ev2",
        summary: "Second cited event",
        event_type: "ingest.meeting_note",
        source_ref: null,
      }),
    ];
    const calls = mockFetch(() => ({ ok: true, body: { events } }));
    render(
      <CitationPanel
        engagementId="e1"
        ids={["ev1", "ev2"]}
        title="LiDAR ingest"
        open={true}
        onClose={() => undefined}
      />,
    );
    await waitFor(() => expect(screen.getByText("First cited event")).toBeTruthy());
    expect(screen.getByText("Second cited event")).toBeTruthy();
    expect(screen.getByText("LiDAR ingest")).toBeTruthy();
    expect(screen.getByText(/2 cited events/)).toBeTruthy();
    // Source_ref renders for events that have one.
    expect(screen.getByText("https://example/em/1")).toBeTruthy();
    // The BFF was called with the ids query-string.
    expect(calls.length).toBe(1);
    expect(calls[0]).toContain("/api/bff/engagements/e1/events");
    expect(calls[0]).toContain("ids=ev1%2Cev2");
  });

  it("does not fetch and renders the empty-state when ids is empty", async () => {
    const calls = mockFetch(() => ({ ok: true, body: { events: [] } }));
    render(
      <CitationPanel
        engagementId="e1"
        ids={[]}
        title="Lonely node"
        open={true}
        onClose={() => undefined}
      />,
    );
    await waitFor(() => expect(screen.getByText(/No source events to show/)).toBeTruthy());
    expect(calls.length).toBe(0);
    expect(screen.getByText(/No source events cited/)).toBeTruthy();
  });

  it("does not fetch when closed", () => {
    const calls = mockFetch(() => ({ ok: true, body: { events: [mkEvent()] } }));
    render(
      <CitationPanel
        engagementId="e1"
        ids={["ev1"]}
        title="Closed"
        open={false}
        onClose={() => undefined}
      />,
    );
    expect(calls.length).toBe(0);
  });

  it("renders an error message when the BFF call fails", async () => {
    mockFetch(() => ({ ok: false, body: { error: "boom" }, text: "boom" }));
    render(
      <CitationPanel
        engagementId="e1"
        ids={["ev1"]}
        title="Broken"
        open={true}
        onClose={() => undefined}
      />,
    );
    await waitFor(() => {
      const para = document.querySelector("p.text-error-700");
      expect(para).toBeTruthy();
      expect(para?.textContent?.length).toBeGreaterThan(0);
    });
  });

  it("close button calls onClose", async () => {
    mockFetch(() => ({ ok: true, body: { events: [mkEvent()] } }));
    const onClose = vi.fn();
    render(
      <CitationPanel
        engagementId="e1"
        ids={["ev1"]}
        title="LiDAR ingest"
        open={true}
        onClose={onClose}
      />,
    );
    await waitFor(() =>
      expect(screen.getByText("Stakeholder confirmed the pilot date")).toBeTruthy(),
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /close/i }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });
});
