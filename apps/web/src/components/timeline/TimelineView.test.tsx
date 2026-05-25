import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TimelineView } from "./TimelineView.client";

type FetchHandler = (url: string) => { ok: boolean; body: unknown; text?: string };

function mockFetch(handler: FetchHandler) {
  const calls: string[] = [];
  const fetchMock = vi.fn((url: string) => {
    calls.push(url);
    const r = handler(url);
    return Promise.resolve({
      ok: r.ok,
      status: r.ok ? 200 : 500,
      json: () => Promise.resolve(r.body),
      text: () => Promise.resolve(r.text ?? JSON.stringify(r.body)),
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

const sampleEvent = {
  id: "ev1",
  engagement_id: "e1",
  occurred_at: "2026-05-20T10:00:00Z",
  recorded_at: "2026-05-20T10:00:01Z",
  actor_kind: "user",
  actor_id: "u1",
  source_kind: "email_ingest",
  source_ref: "imap://abc",
  summary: "First email landed",
  detail: { subject: "Hello" },
  caused_by_ids: ["evX"],
  affects: [{ entity_kind: "matrix_node", entity_id: "n1" }],
};

describe("TimelineView", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the empty state when the BFF returns no events", async () => {
    mockFetch(() => ({ ok: true, body: { events: [] } }));
    render(<TimelineView engagementId="e1" />);
    await waitFor(() => expect(screen.queryByTestId("timeline-loading")).toBeNull());
    expect(screen.getByText(/No events recorded yet/)).toBeTruthy();
  });

  it("renders rows from the BFF response", async () => {
    mockFetch(() => ({ ok: true, body: { events: [sampleEvent] } }));
    render(<TimelineView engagementId="e1" />);
    await waitFor(() => expect(screen.getByText("First email landed")).toBeTruthy());
    expect(screen.getByTestId(`timeline-row-${sampleEvent.id}`)).toBeTruthy();
  });

  it("refetches when filters change (source_kind included in query string)", async () => {
    const calls = mockFetch(() => ({ ok: true, body: { events: [sampleEvent] } }));
    render(<TimelineView engagementId="e1" />);
    await waitFor(() => expect(screen.getByText("First email landed")).toBeTruthy());

    const initialCallCount = calls.length;
    const emailIngestCheckbox = screen.getByLabelText("Email ingest");
    fireEvent.click(emailIngestCheckbox);

    await waitFor(() => expect(calls.length).toBeGreaterThan(initialCallCount));
    const lastUrl = calls[calls.length - 1];
    expect(lastUrl).toMatch(/source_kind=email_ingest/);
  });

  it("opens the drawer when a row is clicked", async () => {
    mockFetch(() => ({ ok: true, body: { events: [sampleEvent] } }));
    render(<TimelineView engagementId="e1" />);
    await waitFor(() => expect(screen.getByText("First email landed")).toBeTruthy());

    const row = screen.getByTestId(`timeline-row-${sampleEvent.id}`);
    fireEvent.click(row);

    await waitFor(() => expect(screen.getByTestId("timeline-event-drawer")).toBeTruthy());
    expect(screen.getByTestId("timeline-event-detail").textContent).toContain("Hello");
    expect(screen.getByText(/Caused by \(1\)/)).toBeTruthy();
    expect(screen.getByText(/Affects \(1\)/)).toBeTruthy();
  });

  it("renders the BFF error message inline when the request fails", async () => {
    mockFetch(() => ({
      ok: false,
      body: { error: "boom", userMessage: "Could not load." },
      text: JSON.stringify({ error: "boom", userMessage: "Could not load." }),
    }));
    render(<TimelineView engagementId="e1" />);
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("Could not load."));
  });
});
