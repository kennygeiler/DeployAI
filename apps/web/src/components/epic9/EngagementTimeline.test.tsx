import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: vi.fn(),
    push: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
  }),
  usePathname: () => "/engagements/e1/timeline",
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

// Now that EngagementTimeline always fetches /ledger, tests feed the ledger
// event shape (source_kind/source_ref/detail/etc.) instead of the legacy
// /timeline event shape. The component maps source_kind → event_type for the
// list view via ledgerToTimelineEvent.
type LedgerEvent = {
  id: string;
  engagement_id: string | null;
  occurred_at: string;
  recorded_at: string;
  actor_kind: string;
  actor_id: string | null;
  source_kind: string;
  source_ref: string | null;
  summary: string;
  detail: Record<string, unknown>;
  caused_by_ids: string[];
  affects: Array<{ entity_kind: string; entity_id: string }>;
};

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
    const mkLedger = (over: Partial<LedgerEvent>): LedgerEvent => ({
      id: "x",
      engagement_id: "e1",
      occurred_at: "2026-01-01T00:00:00Z",
      recorded_at: "2026-01-01T00:00:00Z",
      actor_kind: "user",
      actor_id: null,
      source_kind: "manual_capture",
      source_ref: null,
      summary: "",
      detail: {},
      caused_by_ids: [],
      affects: [],
      ...over,
    });
    const events: LedgerEvent[] = [
      mkLedger({
        id: "a",
        occurred_at: "2026-05-05T10:00:00Z",
        source_kind: "email_ingest",
        summary: "Older-week event",
      }),
      mkLedger({
        id: "b",
        occurred_at: "2026-05-12T15:00:00Z",
        source_kind: "meeting_webhook",
        source_ref: "https://example/notes/42",
        summary: "Recent week event one",
      }),
      mkLedger({
        id: "c",
        occurred_at: "2026-05-14T09:00:00Z",
        source_kind: "manual_capture",
        summary: "Recent week event two",
      }),
    ];
    mockFetch(() => ({ ok: true, body: { events } }));
    render(<EngagementTimeline engagementId="e1" />);
    await waitFor(() => expect(screen.getByText("Recent week event two")).toBeTruthy());

    expect(screen.getByText("Older-week event")).toBeTruthy();
    expect(screen.getByText("Recent week event one")).toBeTruthy();

    const headings = screen.getAllByRole("heading", { level: 3 });
    expect(headings.length).toBe(2);
    const [newer, older] = headings;
    expect(newer?.textContent).toMatch(/May 11/);
    expect(older?.textContent).toMatch(/May 4/);

    expect(screen.getByText("https://example/notes/42")).toBeTruthy();

    expect(screen.getByText("email_ingest")).toBeTruthy();
  });

  it("renders the BFF error message inline when the request fails", async () => {
    mockFetch(() => ({ ok: false, body: { error: "boom" }, text: "boom" }));
    render(<EngagementTimeline engagementId="e1" />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    expect(screen.queryByText(/No interactions yet/)).toBeNull();
    const para = document.querySelector("p.text-error-700");
    expect(para).toBeTruthy();
    expect(para?.textContent?.length).toBeGreaterThan(0);
  });
});
