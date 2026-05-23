import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), forward: vi.fn() }),
}));

import { EventSearch } from "./EventSearch.client";

type CallRecord = { url: string; method: string };

function mockFetch(handler: (call: CallRecord) => { ok: boolean; status?: number; body: unknown }) {
  const calls: CallRecord[] = [];
  const fetchMock = vi.fn((url: string, init?: { method?: string }) => {
    const method = init?.method ?? "GET";
    const record: CallRecord = { url, method };
    calls.push(record);
    const res = handler(record);
    return Promise.resolve({
      ok: res.ok,
      status: res.status ?? (res.ok ? 200 : 500),
      json: () => Promise.resolve(res.body),
      text: () =>
        Promise.resolve(typeof res.body === "string" ? res.body : JSON.stringify(res.body)),
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

describe("EventSearch", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the empty initial state copy and does not fetch", () => {
    const calls = mockFetch(() => ({ ok: true, body: { results: [] } }));
    render(<EventSearch />);
    expect(
      screen.getByText(/Search every email, meeting note, and field note in your tenant\./),
    ).toBeTruthy();
    expect(calls).toHaveLength(0);
  });

  it("types a query and renders the returned results", async () => {
    const calls = mockFetch((call) => {
      if (call.url.startsWith("/api/bff/search")) {
        return {
          ok: true,
          body: {
            results: [
              {
                id: "evt-1",
                engagement_id: "eng-1",
                occurred_at: "2026-05-01T10:00:00Z",
                event_type: "ingest.email",
                source_ref: null,
                snippet: "We need a LiDAR vendor for the rollout",
              },
              {
                id: "evt-2",
                engagement_id: null,
                occurred_at: "2026-05-02T11:00:00Z",
                event_type: "ingest.meeting_note",
                source_ref: null,
                snippet: "Discussed LiDAR procurement",
              },
            ],
          },
        };
      }
      return { ok: false, body: "unexpected" };
    });

    const user = userEvent.setup();
    render(<EventSearch />);
    await user.type(screen.getByLabelText("Query"), "LiDAR");

    await waitFor(() => {
      expect(screen.getByTestId("event-search-results")).toBeTruthy();
    });
    const list = screen.getByTestId("event-search-results");
    expect(list.children.length).toBe(2);
    expect(screen.getByText(/We need a/)).toBeTruthy();
    expect(screen.getByText(/Discussed/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /Open engagement/i })).toBeTruthy();
    expect(screen.getByText("ingest.email")).toBeTruthy();

    const searchCall = calls.find((c) => c.url.startsWith("/api/bff/search"));
    expect(searchCall).toBeDefined();
    expect(searchCall!.url).toContain("q=LiDAR");
  });

  it("renders the error state when the BFF returns non-OK", async () => {
    mockFetch(() => ({ ok: false, status: 503, body: "service down" }));
    const user = userEvent.setup();
    render(<EventSearch />);
    await user.type(screen.getByLabelText("Query"), "vendor");
    await waitFor(() => {
      expect(screen.getByText(/Search failed/)).toBeTruthy();
    });
  });
});
