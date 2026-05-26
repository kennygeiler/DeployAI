import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

const { routerReplaceMock, searchParamsRef } = vi.hoisted(() => ({
  routerReplaceMock: vi.fn(),
  searchParamsRef: { current: new URLSearchParams() as URLSearchParams },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: routerReplaceMock,
    push: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
  }),
  usePathname: () => "/engagements/e1/timeline",
  useSearchParams: () => searchParamsRef.current,
}));

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

beforeAll(() => {
  class RO {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal("ResizeObserver", RO);
});

import { EngagementTimeline } from "../EngagementTimeline.client";
import type { LedgerEvent } from "@/lib/internal/ledger-cp";

function mkLedger(overrides: Partial<LedgerEvent> = {}): LedgerEvent {
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

function mockFetch(body: { events: unknown[] }) {
  const fetchMock = vi.fn(() =>
    Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(body),
      text: () => Promise.resolve(""),
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => {
  routerReplaceMock.mockClear();
  searchParamsRef.current = new URLSearchParams();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("EngagementTimeline — view toggle", () => {
  it("defaults to list view and renders list items", async () => {
    mockFetch({
      events: [
        {
          id: "a",
          occurred_at: "2026-05-20T10:00:00Z",
          event_type: "ingest.email",
          source_ref: null,
          summary: "list event a",
        },
      ],
    });
    render(<EngagementTimeline engagementId="e1" />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    expect(screen.getByText("list event a")).toBeTruthy();
    expect(screen.queryByTestId("horizontal-timeline")).toBeNull();
    const listBtn = screen.getByTestId("timeline-view-toggle-list");
    expect(listBtn.getAttribute("aria-pressed")).toBe("true");
  });

  it("renders the horizontal SVG when initialView='horizontal'", async () => {
    mockFetch({ events: [mkLedger({ id: "h1", summary: "horizontal event" })] });
    render(<EngagementTimeline engagementId="e1" initialView="horizontal" />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    expect(screen.getByTestId("horizontal-timeline")).toBeTruthy();
    expect(screen.getByTestId("horizontal-timeline-event-h1")).toBeTruthy();
    const horizBtn = screen.getByTestId("timeline-view-toggle-horizontal");
    expect(horizBtn.getAttribute("aria-pressed")).toBe("true");
  });

  it("renders horizontal view when URL has ?view=horizontal", async () => {
    searchParamsRef.current = new URLSearchParams("view=horizontal");
    mockFetch({ events: [mkLedger({ id: "u1", summary: "url horizontal event" })] });
    render(<EngagementTimeline engagementId="e1" />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    expect(screen.getByTestId("horizontal-timeline")).toBeTruthy();
    expect(screen.getByTestId("horizontal-timeline-event-u1")).toBeTruthy();
  });

  it("switches view when the toggle is clicked and updates the URL", async () => {
    mockFetch({ events: [mkLedger({ id: "t1", summary: "toggle event" })] });
    render(<EngagementTimeline engagementId="e1" />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());

    const horizBtn = screen.getByTestId("timeline-view-toggle-horizontal");
    fireEvent.click(horizBtn);

    await waitFor(() => {
      expect(screen.queryByTestId("horizontal-timeline")).not.toBeNull();
    });
    expect(routerReplaceMock).toHaveBeenCalled();
    const urls = routerReplaceMock.mock.calls.map((c) => c[0] as string);
    expect(urls.some((u) => u.includes("view=horizontal"))).toBe(true);
  });

  it("preserves the active source-kind filter across view modes", async () => {
    mockFetch({
      events: [
        mkLedger({ id: "x", summary: "shown event", source_kind: "email_ingest" }),
        mkLedger({ id: "y", summary: "hidden event", source_kind: "meeting_webhook" }),
      ],
    });
    render(
      <EngagementTimeline
        engagementId="e1"
        initialView="horizontal"
        initialSourceKinds={["email_ingest"]}
      />,
    );
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    expect(screen.getByTestId("horizontal-timeline-event-x")).toBeTruthy();
    expect(screen.queryByTestId("horizontal-timeline-event-y")).toBeNull();
  });

  it("clicking a circle in horizontal view navigates to ?event=<id>", async () => {
    mockFetch({ events: [mkLedger({ id: "click-id", summary: "click me" })] });
    render(<EngagementTimeline engagementId="e1" initialView="horizontal" />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    const circle = screen.getByTestId("horizontal-timeline-event-click-id");
    fireEvent.click(circle);
    await waitFor(() => {
      expect(routerReplaceMock).toHaveBeenCalled();
    });
    const urls = routerReplaceMock.mock.calls.map((c) => c[0] as string);
    expect(urls.some((u) => u.includes("event=click-id"))).toBe(true);
    expect(urls.some((u) => u.includes("view=horizontal"))).toBe(true);
  });

  it("highlights the focused event with a pulse ring when ?event=<id> matches in horizontal view", async () => {
    const EVENT_ID = "22222222-2222-4222-8222-222222222222";
    mockFetch({
      events: [mkLedger({ id: EVENT_ID, summary: "pulse target" })],
    });
    render(<EngagementTimeline engagementId="e1" initialView="horizontal" eventId={EVENT_ID} />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    await waitFor(() => {
      expect(screen.getByTestId(`horizontal-timeline-pulse-${EVENT_ID}`)).toBeTruthy();
    });
  });
});
