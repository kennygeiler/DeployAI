import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  AskKennyBar,
  deriveSuggestedQuestions,
} from "@/components/engagements/brief/AskKennyBar.client";
import type { MatrixNode } from "@/lib/bff/matrix-types";

function mkNode(id: string, node_type: string, title: string, status: string | null): MatrixNode {
  return {
    id,
    engagement_id: "e1",
    node_type,
    title,
    identity_node_id: null,
    attributes: {},
    status,
    evidence_event_ids: [],
    created_at: "2026-05-09T00:00:00Z",
    updated_at: "2026-05-09T00:00:00Z",
  } as MatrixNode;
}

function stubOracleFetch() {
  const calls: string[] = [];
  const fetchMock = vi.fn((url: string) => {
    calls.push(url);
    if (url.includes("/oracle/history")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ conversation_id: null, turns: [] }),
      });
    }
    // Stream endpoints report unavailable; JSON fallback replies.
    if (url.includes("/oracle/chat/stream")) {
      return Promise.resolve({ ok: false, status: 503, body: null, text: () => Promise.resolve("") });
    }
    if (url.includes("/oracle/chat")) {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            turn_id: "t1",
            conversation_id: "c1",
            content: "Grounded answer",
            tokens_used: 10,
          }),
      });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

describe("deriveSuggestedQuestions", () => {
  it("derives from open risks and recent decisions, topped up with fallbacks", () => {
    const qs = deriveSuggestedQuestions({
      nodes: [mkNode("n1", "risk", "Calibration slip", "open")],
      changes: [
        {
          occurred_at: "2026-08-10T00:00:00Z",
          kind: "decision_accepted",
          title: "Decision accepted: Phase 2 rollout",
          actor_display_name: null,
        },
      ],
    });
    expect(qs).toHaveLength(3);
    expect(qs[0]).toContain("Calibration slip");
    expect(qs[1]).toContain("Phase 2 rollout");
  });

  it("falls back to generic DRM questions on an empty engagement", () => {
    const qs = deriveSuggestedQuestions({ nodes: [], changes: [] });
    expect(qs).toHaveLength(3);
    expect(qs[0]).toMatch(/changed on this deal/);
  });
});

describe("AskKennyBar", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the input and three suggested questions", () => {
    stubOracleFetch();
    render(<AskKennyBar engagementId="e1" nodes={[]} changes={[]} />);
    expect(screen.getByLabelText("Ask Agent Kenny")).toBeTruthy();
    expect(screen.getAllByTestId("ask-kenny-suggestion")).toHaveLength(3);
    // No overlay until a question is submitted.
    expect(screen.queryByTestId("ask-kenny-overlay")).toBeNull();
  });

  it("opens the full-width chat overlay and auto-sends the typed question", async () => {
    const calls = stubOracleFetch();
    const user = userEvent.setup();
    render(<AskKennyBar engagementId="e1" nodes={[]} changes={[]} />);

    await user.type(screen.getByLabelText("Ask Agent Kenny"), "What changed?");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    const overlay = await screen.findByTestId("ask-kenny-overlay");
    expect(overlay).toBeTruthy();
    const panel = await screen.findByTestId("oracle-chat-panel");
    expect(panel.getAttribute("data-variant")).toBe("overlay");

    // The seeded question was sent through the existing chat transport.
    await waitFor(() => expect(calls.some((u) => u.includes("/oracle/chat"))).toBe(true));
  });

  it("opens the overlay from a suggestion chip", async () => {
    stubOracleFetch();
    const user = userEvent.setup();
    render(<AskKennyBar engagementId="e1" nodes={[]} changes={[]} />);

    await user.click(screen.getAllByTestId("ask-kenny-suggestion")[0]!);
    expect(await screen.findByTestId("ask-kenny-overlay")).toBeTruthy();
  });

  it("closes the overlay via the backdrop", async () => {
    stubOracleFetch();
    const user = userEvent.setup();
    render(<AskKennyBar engagementId="e1" nodes={[]} changes={[]} />);

    await user.click(screen.getByTestId("ask-kenny-open-chat"));
    await screen.findByTestId("ask-kenny-overlay");
    await user.click(screen.getByLabelText("Close chat"));
    await waitFor(() => expect(screen.queryByTestId("ask-kenny-overlay")).toBeNull());
  });
});
