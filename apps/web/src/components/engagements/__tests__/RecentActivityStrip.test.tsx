import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RecentActivityStrip } from "@/components/engagements/RecentActivityStrip.client";
import type { LedgerEvent } from "@/lib/internal/ledger-cp";

function mkEvent(overrides: Partial<LedgerEvent> = {}): LedgerEvent {
  return {
    id: "evt-1",
    engagement_id: "e1",
    occurred_at: "2026-05-20T10:00:00Z",
    recorded_at: "2026-05-20T10:00:01Z",
    actor_kind: "user",
    actor_id: "u-1",
    source_kind: "email_ingest",
    source_ref: null,
    summary: "Bluestate kickoff notes received",
    detail: {},
    caused_by_ids: [],
    affects: [],
    ...overrides,
  };
}

function mockFetch(body: { events: LedgerEvent[] } | null, ok = true) {
  const calls: string[] = [];
  const fetchMock = vi.fn((url: string) => {
    calls.push(url);
    return Promise.resolve({
      ok,
      status: ok ? 200 : 500,
      json: () => Promise.resolve(body ?? { events: [] }),
      text: () => Promise.resolve(""),
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

describe("RecentActivityStrip", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the empty-state placeholder when no events come back", async () => {
    mockFetch({ events: [] });
    render(<RecentActivityStrip engagementId="e1" />);
    await waitFor(() => expect(screen.queryByText(/Loading recent activity/)).toBeNull());
    expect(screen.getByText("No recent activity.")).toBeTruthy();
  });

  it("renders 5 cards in a scroll container with an aria-label of recent activity", async () => {
    const events = Array.from({ length: 5 }, (_v, i) =>
      mkEvent({
        id: `e${i}`,
        summary: `Summary ${i}`,
        source_kind: i % 2 === 0 ? "email_ingest" : "meeting_webhook",
      }),
    );
    const calls = mockFetch({ events });
    render(<RecentActivityStrip engagementId="e1" />);
    await waitFor(() => expect(screen.getByTestId("recent-activity-list")).toBeTruthy());

    expect(calls[0]).toContain("/api/bff/engagements/e1/ledger?limit=5");

    const section = screen.getByLabelText("recent activity");
    expect(section).toBeTruthy();

    const cards = section.querySelectorAll("a[data-testid^='recent-activity-card-']");
    expect(cards.length).toBe(5);
    cards.forEach((card) => {
      expect(card.getAttribute("aria-label")?.length).toBeGreaterThan(0);
      const href = card.getAttribute("href") ?? "";
      expect(href).toMatch(/\/engagements\/e1\/timeline\?event=/);
    });

    // Scroll container marker — horizontal overflow.
    const list = screen.getByTestId("recent-activity-list");
    expect(list.className).toMatch(/overflow-x-auto/);
  });

  it("caps the visible cards at 5 even if the BFF returns more", async () => {
    const events = Array.from({ length: 8 }, (_v, i) =>
      mkEvent({ id: `e${i}`, summary: `Summary ${i}` }),
    );
    mockFetch({ events });
    render(<RecentActivityStrip engagementId="e1" />);
    await waitFor(() => expect(screen.getByTestId("recent-activity-list")).toBeTruthy());
    const cards = screen
      .getByTestId("recent-activity-list")
      .querySelectorAll("a[data-testid^='recent-activity-card-']");
    expect(cards.length).toBe(5);
  });

  it("surfaces an error message when the BFF call fails", async () => {
    mockFetch(null, false);
    render(<RecentActivityStrip engagementId="e1" />);
    await waitFor(() => expect(screen.queryByText(/Loading recent activity/)).toBeNull());
    expect(screen.getByRole("alert")).toBeTruthy();
  });
});
