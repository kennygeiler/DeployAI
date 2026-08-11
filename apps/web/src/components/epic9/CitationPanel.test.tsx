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
      const para = document.querySelector("p.text-red-ink");
      expect(para).toBeTruthy();
      expect(para?.textContent?.length).toBeGreaterThan(0);
    });
  });

  it("flags a citation as disputed (E3) and shows the flagged badge", async () => {
    const calls: Array<{ url: string; method: string; body?: string }> = [];
    const fetchMock = vi.fn((url: string, init?: { method?: string; body?: string }) => {
      calls.push({ url, method: init?.method ?? "GET", body: init?.body });
      if (url.includes("/citations/dispute")) {
        return Promise.resolve({
          ok: true,
          status: 201,
          json: () => Promise.resolve({ item: { id: "ri1", kind: "citation_dispute" } }),
          text: () => Promise.resolve(""),
        });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ events: [mkEvent()] }),
        text: () => Promise.resolve(""),
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <CitationPanel
        engagementId="e1"
        ids={["ev1"]}
        title="Answer sources"
        open={true}
        onClose={() => undefined}
        turnId="turn-42"
      />,
    );
    await waitFor(() =>
      expect(screen.getByText("Stakeholder confirmed the pilot date")).toBeTruthy(),
    );

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /flag citation ev1/i }));
    await user.type(screen.getByLabelText("Why is this citation wrong?"), "wrong stakeholder");
    await user.click(screen.getByRole("button", { name: "Submit" }));

    await waitFor(() => expect(screen.getByText("flagged")).toBeTruthy());
    const post = calls.find((c) => c.method === "POST");
    expect(post?.url).toContain("/api/bff/engagements/e1/citations/dispute");
    const body = JSON.parse(post?.body ?? "{}") as Record<string, unknown>;
    expect(body.citation_id).toBe("ev1");
    expect(body.turn_id).toBe("turn-42");
    expect(body.reason).toBe("wrong stakeholder");
  });

  it("requires a reason before submitting a dispute", async () => {
    const calls = mockFetch(() => ({ ok: true, body: { events: [mkEvent()] } }));
    render(
      <CitationPanel
        engagementId="e1"
        ids={["ev1"]}
        title="Answer sources"
        open={true}
        onClose={() => undefined}
      />,
    );
    await waitFor(() =>
      expect(screen.getByText("Stakeholder confirmed the pilot date")).toBeTruthy(),
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /flag citation ev1/i }));
    await user.click(screen.getByRole("button", { name: "Submit" }));
    // No dispute POST happened — only the initial events GET.
    expect(calls.length).toBe(1);
    expect(screen.queryByText("flagged")).toBeNull();
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
