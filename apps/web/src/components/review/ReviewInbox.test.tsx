import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ReviewItem } from "@/lib/bff/review-types";

import { ReviewInbox } from "./ReviewInbox.client";

function mkEscalation(overrides: Partial<ReviewItem> = {}): ReviewItem {
  return {
    id: "ri-esc-1",
    tenant_id: "t1",
    engagement_id: "e1",
    kind: "agent_escalation",
    status: "open",
    payload: {
      question: "Who owns the security review?",
      reason: "citation verification failed twice",
      context_refs: [],
    },
    created_by: "agent:kenny",
    resolved_by: null,
    resolution_note: null,
    created_at: "2026-08-10T12:00:00Z",
    resolved_at: null,
    ...overrides,
  };
}

function mkDispute(overrides: Partial<ReviewItem> = {}): ReviewItem {
  return mkEscalation({
    id: "ri-disp-1",
    kind: "citation_dispute",
    payload: { turn_id: "turn-1", citation_id: "ev-9", reason: "wrong stakeholder" },
    created_by: "user:kenny",
    ...overrides,
  });
}

type Handler = (url: string, init?: { method?: string; body?: string }) => unknown | null;

function mockFetch(handler: Handler) {
  const calls: Array<{ url: string; method: string; body?: string }> = [];
  const fetchMock = vi.fn((url: string, init?: { method?: string; body?: string }) => {
    calls.push({ url, method: init?.method ?? "GET", body: init?.body });
    const body = handler(url, init);
    if (body === null) {
      return Promise.resolve({
        ok: false,
        status: 500,
        json: () => Promise.resolve({ error: "boom" }),
        text: () => Promise.resolve("boom"),
      });
    }
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

const baseHandler: Handler = (url) => {
  if (url.includes("/api/bff/review/items")) {
    return { items: [mkEscalation(), mkDispute()] };
  }
  if (url === "/api/bff/engagements") {
    return { engagements: [{ id: "11111111-1111-4111-8111-111111111111", name: "Acme pilot" }] };
  }
  return {};
};

describe("ReviewInbox", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("lists open review items with kind badges", async () => {
    mockFetch(baseHandler);
    render(<ReviewInbox />);
    await waitFor(() => expect(screen.getByText("Who owns the security review?")).toBeTruthy());
    expect(screen.getByText(/Disputed citation/)).toBeTruthy();
    expect(screen.getByText("agent escalation")).toBeTruthy();
    expect(screen.getByText("citation dispute")).toBeTruthy();
  });

  it("filters by kind tab client-side and passes kind to the BFF", async () => {
    const calls = mockFetch(baseHandler);
    render(<ReviewInbox />);
    await waitFor(() => expect(screen.getByText("Who owns the security review?")).toBeTruthy());

    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Escalations" }));

    await waitFor(() =>
      expect(
        calls.some(
          (c) => c.url.includes("/api/bff/review/items") && c.url.includes("kind=agent_escalation"),
        ),
      ).toBe(true),
    );
  });

  it("shows the Wave 3 empty state on the commitments tab", async () => {
    mockFetch((url, init) => {
      if (url.includes("/api/bff/review/items")) {
        return { items: [] };
      }
      return baseHandler(url, init);
    });
    render(<ReviewInbox />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());

    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Commitments" }));
    await waitFor(() =>
      expect(screen.getByText(/commitment tracking ships in Wave 3/i)).toBeTruthy(),
    );
  });

  it("resolves an escalation with an answer (E2) and drops the card optimistically", async () => {
    const calls = mockFetch((url, init) => {
      if (url.includes("/resolve")) {
        return { item: { ...mkEscalation(), status: "resolved" } };
      }
      return baseHandler(url, init);
    });
    render(<ReviewInbox />);
    await waitFor(() => expect(screen.getByText("Who owns the security review?")).toBeTruthy());

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Answer" }));
    await user.type(
      screen.getByLabelText(/Answer \(recorded as canonical knowledge/i),
      "The FDE owns it.",
    );
    await user.type(screen.getByLabelText(/^Citations \(event ids/i), "ev-1, ev-2");
    await user.click(screen.getByRole("button", { name: "Submit answer" }));

    await waitFor(() => expect(screen.queryByText("Who owns the security review?")).toBeNull());
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.url).toContain("/api/bff/review/items/ri-esc-1/resolve");
    const body = JSON.parse(post.body ?? "{}") as Record<string, unknown>;
    expect(body.answer_text).toBe("The FDE owns it.");
    expect(body.answer_citations).toEqual(["ev-1", "ev-2"]);
  });

  it("requires an answer before resolving an escalation", async () => {
    const calls = mockFetch(baseHandler);
    render(<ReviewInbox />);
    await waitFor(() => expect(screen.getByText("Who owns the security review?")).toBeTruthy());

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Answer" }));
    await user.click(screen.getByRole("button", { name: "Submit answer" }));
    expect(calls.some((c) => c.method === "POST")).toBe(false);
    // Card is still there.
    expect(screen.getByText("Who owns the security review?")).toBeTruthy();
  });

  it("dismisses an item and restores it when the BFF call fails", async () => {
    mockFetch((url, init) => {
      if (url.includes("/dismiss")) {
        return null; // 500
      }
      if (url.includes("/api/bff/review/items")) {
        return { items: [mkDispute()] };
      }
      return baseHandler(url, init);
    });
    render(<ReviewInbox />);
    await waitFor(() => expect(screen.getByText(/Disputed citation/)).toBeTruthy());

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Dismiss" }));

    // Optimistically removed, then restored after the 500.
    await waitFor(() => expect(screen.getByText(/Disputed citation/)).toBeTruthy());
  });

  it("resolves a citation dispute with the plain Resolve action", async () => {
    const calls = mockFetch((url, init) => {
      if (url.includes("/resolve")) {
        return { item: { ...mkDispute(), status: "resolved" } };
      }
      if (url.includes("/api/bff/review/items")) {
        return { items: [mkDispute()] };
      }
      return baseHandler(url, init);
    });
    render(<ReviewInbox />);
    await waitFor(() => expect(screen.getByText(/Disputed citation/)).toBeTruthy());

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Resolve" }));

    await waitFor(() => expect(screen.queryByText(/Disputed citation/)).toBeNull());
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.url).toContain("/api/bff/review/items/ri-disp-1/resolve");
  });

  it("prompts to select an engagement for extraction proposals, then lists them", async () => {
    const engagementId = "11111111-1111-4111-8111-111111111111";
    mockFetch((url, init) => {
      if (url.includes(`/api/bff/engagements/${engagementId}`)) {
        return {
          matrix: {
            proposals: [
              {
                id: "p1",
                engagement_id: engagementId,
                source_event_id: "ev1",
                proposal_kind: "node",
                payload: { node_type: "risk", title: "Calibration drift" },
                rationale: "Mentioned twice in kickoff",
                status: "pending",
                created_at: "2026-08-10T12:00:00Z",
                decided_at: null,
                decided_by: null,
                result_node_id: null,
                result_edge_id: null,
              },
            ],
          },
        };
      }
      return baseHandler(url, init);
    });
    render(<ReviewInbox />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    expect(screen.getByText(/Select an engagement to include/)).toBeTruthy();

    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Engagement"), engagementId);

    await waitFor(() => expect(screen.getByText(/risk: Calibration drift/)).toBeTruthy());
    expect(screen.getByRole("button", { name: "Accept" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reject" })).toBeTruthy();
  });
});
