import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EngagementTimeline } from "./EngagementTimeline.client";
import type { LedgerEvent } from "@/lib/internal/ledger-cp";

type TimelineEvent = {
  id: string;
  occurred_at: string;
  event_type: string;
  source_ref: string | null;
  summary: string;
};

function mkLedgerEvent(overrides: Partial<LedgerEvent> = {}): LedgerEvent {
  return {
    id: "evt-1",
    engagement_id: "e1",
    occurred_at: "2026-05-20T10:00:00Z",
    recorded_at: "2026-05-20T10:00:01Z",
    actor_kind: "user",
    actor_id: null,
    source_kind: "email_ingest",
    source_ref: null,
    summary: "ledger event",
    detail: {},
    caused_by_ids: [],
    affects: [],
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

describe("EngagementTimeline", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the empty state when the BFF returns no events", async () => {
    mockFetch(() => ({ ok: true, body: { events: [] } }));
    render(<EngagementTimeline engagementId="e1" />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    expect(screen.getByText(/No interactions yet/)).toBeTruthy();
  });

  it("groups events into ISO weeks with newest week first", async () => {
    const events: TimelineEvent[] = [
      // Week of 2026-05-04 (Mon) — 2026-05-10 (Sun)
      {
        id: "a",
        occurred_at: "2026-05-05T10:00:00Z",
        event_type: "ingest.email",
        source_ref: null,
        summary: "Older-week event",
      },
      // Week of 2026-05-11 (Mon) — 2026-05-17 (Sun)
      {
        id: "b",
        occurred_at: "2026-05-12T15:00:00Z",
        event_type: "ingest.meeting_note",
        source_ref: "https://example/notes/42",
        summary: "Recent week event one",
      },
      {
        id: "c",
        occurred_at: "2026-05-14T09:00:00Z",
        event_type: "ingest.field_note",
        source_ref: null,
        summary: "Recent week event two",
      },
    ];
    mockFetch(() => ({ ok: true, body: { events } }));
    render(<EngagementTimeline engagementId="e1" />);
    await waitFor(() => expect(screen.getByText("Recent week event two")).toBeTruthy());

    // All three summaries render.
    expect(screen.getByText("Older-week event")).toBeTruthy();
    expect(screen.getByText("Recent week event one")).toBeTruthy();

    // The first week heading shown is the newer one. We assert via DOM order.
    const headings = screen.getAllByRole("heading", { level: 3 });
    expect(headings.length).toBe(2);
    const [newer, older] = headings;
    expect(newer?.textContent).toMatch(/May 11/);
    expect(older?.textContent).toMatch(/May 4/);

    // The source_ref renders for the meeting-note event.
    expect(screen.getByText("https://example/notes/42")).toBeTruthy();

    // event_type badge text appears as-is.
    expect(screen.getByText("ingest.email")).toBeTruthy();
  });

  it("renders the BFF error message inline when the request fails", async () => {
    mockFetch(() => ({ ok: false, body: { error: "boom" }, text: "boom" }));
    render(<EngagementTimeline engagementId="e1" />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    // readStrategistBffErrorDescription falls back to status text or body.
    expect(screen.queryByText(/No interactions yet/)).toBeNull();
    // An error paragraph is rendered (any non-empty error string is fine).
    const para = document.querySelector("p.text-error-700");
    expect(para).toBeTruthy();
    expect(para?.textContent?.length).toBeGreaterThan(0);
  });

  it("shows the stakeholder chip + filters ledger events by evidence id or actor email", async () => {
    const events = [
      mkLedgerEvent({
        id: "match-evidence",
        actor_id: null,
        summary: "Match via evidence id",
      }),
      mkLedgerEvent({
        id: "match-actor",
        actor_id: "alice@example.com",
        summary: "Match via actor email",
      }),
      mkLedgerEvent({
        id: "drop-me",
        actor_id: "bob@example.com",
        summary: "Should be filtered out",
      }),
    ];
    const calls = mockFetch(() => ({ ok: true, body: { events } }));
    render(
      <EngagementTimeline
        engagementId="e1"
        stakeholderFilter={{
          id: "stk-1",
          title: "Alice Sponsor",
          email: "Alice@example.com",
          evidenceEventIds: ["match-evidence"],
          clearHref: "/engagements/e1/timeline",
        }}
      />,
    );
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());

    // Hits the ledger BFF when filter is active (not the simpler /timeline endpoint).
    expect(calls.some((u) => u.includes("/ledger?limit=500"))).toBe(true);

    // Chip shown with stakeholder title + clear link.
    expect(screen.getByTestId("stakeholder-chip")).toBeTruthy();
    expect(screen.getByText("Alice Sponsor")).toBeTruthy();
    const clear = screen.getByTestId("stakeholder-chip-clear");
    expect(clear.getAttribute("href")).toBe("/engagements/e1/timeline");

    // Only the two matching events render.
    expect(screen.getByText("Match via evidence id")).toBeTruthy();
    expect(screen.getByText("Match via actor email")).toBeTruthy();
    expect(screen.queryByText("Should be filtered out")).toBeNull();
  });

  it("renders an empty-state message specific to the active stakeholder filter", async () => {
    mockFetch(() => ({ ok: true, body: { events: [] } }));
    render(
      <EngagementTimeline
        engagementId="e1"
        stakeholderFilter={{
          id: "stk-1",
          title: "Alice Sponsor",
          email: "alice@example.com",
          evidenceEventIds: [],
          clearHref: "/engagements/e1/timeline",
        }}
      />,
    );
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    expect(screen.getByText(/No timeline events match Alice Sponsor/)).toBeTruthy();
  });
});
