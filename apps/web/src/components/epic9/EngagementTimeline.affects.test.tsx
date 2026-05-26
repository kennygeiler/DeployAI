import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: vi.fn(),
    push: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
  }),
  usePathname: () => "/engagements/eng-1/timeline",
  useSearchParams: () => new URLSearchParams(),
}));

beforeAll(() => {
  class RO {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal("ResizeObserver", RO);
});

import { EngagementTimeline } from "./EngagementTimeline.client";
import type { LedgerEvent } from "@/lib/internal/ledger-cp";

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

function mockFetch(body: { events: LedgerEvent[] }) {
  const calls: string[] = [];
  const fetchMock = vi.fn((url: string) => {
    calls.push(url);
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(body),
      text: () => Promise.resolve(""),
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

describe("EngagementTimeline — affects filter", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetches via affects_entity_kind/id when affectsFilter is set", async () => {
    const events = [
      mkLedgerEvent({ id: "a", summary: "Created node" }),
      mkLedgerEvent({ id: "b", summary: "Updated node" }),
    ];
    const calls = mockFetch({ events });
    render(
      <EngagementTimeline
        engagementId="eng-1"
        affectsFilter={{
          nodeId: "11111111-1111-4111-8111-111111111111",
          nodeTitle: "Alice Sponsor",
          clearHref: "/engagements/eng-1/timeline",
        }}
      />,
    );
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());

    expect(
      calls.some(
        (u) =>
          u.includes("/ledger?") &&
          u.includes("affects_entity_kind=matrix_node") &&
          u.includes("affects_entity_id=11111111-1111-4111-8111-111111111111"),
      ),
    ).toBe(true);

    expect(screen.getByText("Created node")).toBeTruthy();
    expect(screen.getByText("Updated node")).toBeTruthy();
  });

  it("shows the 'Showing events affecting <title>' chip with a clearing link", async () => {
    const events = [mkLedgerEvent({ id: "a", summary: "Event a" })];
    mockFetch({ events });
    render(
      <EngagementTimeline
        engagementId="eng-1"
        affectsFilter={{
          nodeId: "11111111-1111-4111-8111-111111111111",
          nodeTitle: "Alice Sponsor",
          clearHref: "/engagements/eng-1/timeline",
        }}
      />,
    );
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());

    const chip = screen.getByTestId("affects-chip");
    expect(chip).toBeTruthy();
    expect(chip.textContent).toMatch(/Showing events affecting/);
    expect(chip.textContent).toMatch(/Alice Sponsor/);

    const clear = screen.getByTestId("affects-chip-clear");
    expect(clear.getAttribute("href")).toBe("/engagements/eng-1/timeline");
  });

  it("renders an empty-state message specific to the active affects filter", async () => {
    mockFetch({ events: [] });
    render(
      <EngagementTimeline
        engagementId="eng-1"
        affectsFilter={{
          nodeId: "11111111-1111-4111-8111-111111111111",
          nodeTitle: "Alice Sponsor",
          clearHref: "/engagements/eng-1/timeline",
        }}
      />,
    );
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    expect(screen.getByText(/No timeline events affect Alice Sponsor/)).toBeTruthy();
  });
});
