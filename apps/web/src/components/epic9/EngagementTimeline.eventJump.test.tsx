import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

const { toastMock } = vi.hoisted(() => ({ toastMock: vi.fn() }));

vi.mock("sonner", () => {
  const t = Object.assign(toastMock, { success: vi.fn(), error: vi.fn() });
  return { toast: t };
});

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

const scrollIntoViewMock = vi.fn();

beforeEach(() => {
  Object.defineProperty(Element.prototype, "scrollIntoView", {
    configurable: true,
    writable: true,
    value: scrollIntoViewMock,
  });
  scrollIntoViewMock.mockClear();
  toastMock.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const EVENT_ID = "22222222-2222-4222-8222-222222222222";

describe("EngagementTimeline — event jump", () => {
  it("highlights and scrolls the matching event card into view", async () => {
    const events = [
      mkLedgerEvent({ id: EVENT_ID, summary: "Target event", source_kind: "email_ingest" }),
      mkLedgerEvent({ id: "other-id", summary: "Other event", source_kind: "email_ingest" }),
    ];
    mockFetch({ events });

    render(<EngagementTimeline engagementId="eng-1" eventId={EVENT_ID} />);

    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    await waitFor(() => {
      const li = screen.getByTestId(`timeline-event-${EVENT_ID}`);
      expect(li.getAttribute("aria-current")).toBe("true");
    });

    expect(scrollIntoViewMock).toHaveBeenCalled();
    const li = screen.getByTestId(`timeline-event-${EVENT_ID}`);
    expect(li.className).toMatch(/bg-warning-100/);
    expect(li.className).toMatch(/ring-warning-400/);
  });

  it("clears the source-kind filter and toasts when the target event would be filtered out", async () => {
    const events = [
      mkLedgerEvent({ id: EVENT_ID, summary: "Target event", source_kind: "email_ingest" }),
      mkLedgerEvent({ id: "other-id", summary: "Other event", source_kind: "meeting_webhook" }),
    ];
    mockFetch({ events });

    render(
      <EngagementTimeline
        engagementId="eng-1"
        eventId={EVENT_ID}
        initialSourceKinds={["meeting_webhook"]}
      />,
    );

    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    await waitFor(() => {
      expect(toastMock).toHaveBeenCalled();
    });
    expect(
      toastMock.mock.calls.some(
        (c) => typeof c[0] === "string" && /Cleared filters/i.test(c[0] as string),
      ),
    ).toBe(true);

    await waitFor(() => {
      expect(screen.queryByTestId("source-kind-chip-meeting_webhook")).toBeNull();
    });

    await waitFor(() => {
      const li = screen.getByTestId(`timeline-event-${EVENT_ID}`);
      expect(li.getAttribute("aria-current")).toBe("true");
    });
  });

  it("toasts 'Event not on this page' when the event id isn't in the loaded set", async () => {
    const events = [mkLedgerEvent({ id: "other-id", summary: "Other event" })];
    mockFetch({ events });

    render(<EngagementTimeline engagementId="eng-1" eventId={EVENT_ID} />);

    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    await waitFor(() => {
      expect(toastMock).toHaveBeenCalled();
    });
    expect(
      toastMock.mock.calls.some(
        (c) => typeof c[0] === "string" && /not on this page/i.test(c[0] as string),
      ),
    ).toBe(true);
  });
});
