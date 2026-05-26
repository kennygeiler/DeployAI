import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OracleChat } from "@/components/engagements/OracleChat.client";

const { toastErrorMock, toastSuccessMock } = vi.hoisted(() => ({
  toastErrorMock: vi.fn(),
  toastSuccessMock: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
    success: toastSuccessMock,
  },
}));

vi.mock("next/link", () => ({
  // Minimal stand-in: tests assert on href + textContent only.
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: React.ReactNode;
  } & React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const EVENT_UUID = "11111111-1111-4111-8111-111111111111";
const NODE_UUID = "22222222-2222-4222-8222-222222222222";
const TURN_ID = "33333333-3333-4333-8333-333333333333";
const CONVO_ID = "44444444-4444-4444-8444-444444444444";

type FetchHandler = (init?: RequestInit) =>
  | { ok: boolean; status?: number; json: () => Promise<unknown>; text?: () => Promise<string> }
  | Promise<{
      ok: boolean;
      status?: number;
      json: () => Promise<unknown>;
      text?: () => Promise<string>;
    }>;

function installFetch(routes: Record<string, FetchHandler>) {
  const calls: Array<{ url: string; method: string; body: unknown }> = [];
  const mock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    let body: unknown = null;
    if (typeof init?.body === "string") {
      try {
        body = JSON.parse(init.body);
      } catch {
        body = init.body;
      }
    }
    calls.push({ url, method, body });
    for (const [pattern, handler] of Object.entries(routes)) {
      if (url.includes(pattern)) {
        const result = await Promise.resolve(handler(init));
        return Object.assign({ text: async () => JSON.stringify(await result.json()) }, result);
      }
    }
    return { ok: true, status: 200, json: async () => ({}), text: async () => "" };
  });
  vi.stubGlobal("fetch", mock);
  return calls;
}

async function openPanel(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: /open/i }));
}

describe("OracleChat", () => {
  beforeEach(() => {
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the panel with collapsed body; Send button is disabled when input is empty", async () => {
    installFetch({
      "/oracle/history": () => ({
        ok: true,
        status: 200,
        json: async () => ({ conversation_id: null, turns: [] }),
      }),
    });

    render(<OracleChat engagementId="e1" />);
    expect(screen.getByTestId("oracle-chat-panel")).toBeTruthy();
    const user = userEvent.setup();
    await openPanel(user);

    const region = await screen.findByRole("region", { name: /mr\. oracle/i });
    expect(region).toBeTruthy();
    const sendBtn = screen.getByRole("button", { name: /^send$/i });
    expect((sendBtn as HTMLButtonElement).disabled).toBe(true);
  });

  it("renders incrementally: optimistic user turn appears, then the oracle reply flips in", async () => {
    let resolveReply:
      | ((value: { ok: boolean; status?: number; json: () => Promise<unknown> }) => void)
      | null = null;
    installFetch({
      "/oracle/history": () => ({
        ok: true,
        status: 200,
        json: async () => ({ conversation_id: null, turns: [] }),
      }),
      "/oracle/chat": () =>
        new Promise((resolve) => {
          resolveReply = resolve;
        }),
    });

    render(<OracleChat engagementId="e1" />);
    const user = userEvent.setup();
    await openPanel(user);

    const input = await screen.findByLabelText(/message mr\. oracle/i);
    await user.type(input, "what should I worry about?");
    const sendBtn = screen.getByRole("button", { name: /^send$/i });
    expect((sendBtn as HTMLButtonElement).disabled).toBe(false);
    await user.click(sendBtn);

    // Optimistic user turn renders immediately while the POST is in flight.
    await waitFor(() => {
      expect(screen.getByText("what should I worry about?")).toBeTruthy();
    });

    // Finalize the streaming-mock fetch — oracle reply flips state to done.
    resolveReply!({
      ok: true,
      status: 200,
      json: async () => ({
        turn_id: TURN_ID,
        conversation_id: CONVO_ID,
        content: `Two open risks. See [event:${EVENT_UUID}].`,
        tokens_used: 314,
      }),
    });

    await waitFor(() => {
      expect(screen.getByText(/two open risks/i)).toBeTruthy();
    });
    // After the reply lands, Send is enabled again + textarea is empty.
    await waitFor(() => {
      expect((screen.getByRole("button", { name: /^send$/i }) as HTMLButtonElement).disabled).toBe(
        true,
      );
    });
  });

  it("surfaces a friendly toast when CP returns 429 budget-exhausted", async () => {
    installFetch({
      "/oracle/history": () => ({
        ok: true,
        status: 200,
        json: async () => ({ conversation_id: null, turns: [] }),
      }),
      "/oracle/chat": () => ({
        ok: false,
        status: 429,
        json: async () => ({
          error: "budget_exhausted",
          code: "oracle_daily_budget",
          userMessage: "Daily LLM budget reached. Try again tomorrow.",
          retry_after_iso: "2026-05-26T00:00:00Z",
        }),
      }),
    });

    render(<OracleChat engagementId="e1" />);
    const user = userEvent.setup();
    await openPanel(user);

    const input = await screen.findByLabelText(/message mr\. oracle/i);
    await user.type(input, "hi");
    await user.click(screen.getByRole("button", { name: /^send$/i }));

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalled();
    });
    const arg = toastErrorMock.mock.calls[0]![0];
    expect(String(arg).toLowerCase()).toContain("daily llm budget reached");
  });

  it("renders cite-links: [event:UUID] resolves to the ledger timeline route", async () => {
    installFetch({
      "/oracle/history": () => ({
        ok: true,
        status: 200,
        json: async () => ({
          conversation_id: CONVO_ID,
          turns: [
            {
              id: TURN_ID,
              conversation_id: CONVO_ID,
              role: "oracle",
              content: `Risk surfaced [event:${EVENT_UUID}] and node [node:${NODE_UUID}].`,
              tokens_used: 200,
              created_at: "2026-05-25T00:00:00Z",
            },
          ],
        }),
      }),
    });

    render(<OracleChat engagementId="e1" />);
    const user = userEvent.setup();
    await openPanel(user);

    const eventLink = await screen.findByTestId("oracle-cite-event");
    expect(eventLink.getAttribute("href")).toBe(`/engagements/e1/timeline?event=${EVENT_UUID}`);
    const nodeLink = screen.getByTestId("oracle-cite-node");
    expect(nodeLink.getAttribute("href")).toBe(`/engagements/e1?node=${NODE_UUID}`);
  });

  it("a11y: panel body has role=region with a label, and the input is a textarea with aria-label", async () => {
    installFetch({
      "/oracle/history": () => ({
        ok: true,
        status: 200,
        json: async () => ({ conversation_id: null, turns: [] }),
      }),
    });

    render(<OracleChat engagementId="e1" />);
    const user = userEvent.setup();
    await openPanel(user);

    // Panel is persistent + non-modal; `role="region"` is the correct ARIA
    // primitive (a dialog requires `aria-modal="true"` to be valid).
    const region = await screen.findByRole("region", { name: /mr\. oracle/i });
    expect(region).toBeTruthy();
    const textarea = within(region).getByLabelText(/message mr\. oracle/i);
    expect(textarea.tagName.toLowerCase()).toBe("textarea");
    // AI-generated disclosure footer.
    expect(within(region).getByText(/ai-generated/i)).toBeTruthy();
  });

  it("uses the shared Button primitive (no raw <button> in the panel body)", async () => {
    installFetch({
      "/oracle/history": () => ({
        ok: true,
        status: 200,
        json: async () => ({ conversation_id: null, turns: [] }),
      }),
    });

    render(<OracleChat engagementId="e1" />);
    const user = userEvent.setup();
    await openPanel(user);

    const region = await screen.findByRole("region", { name: /mr\. oracle/i });
    const sendBtn = within(region).getByRole("button", { name: /^send$/i });
    // The shared <Button> primitive applies `data-slot="button"` via its
    // generated className/attrs — checking for the rounded-md utility is a
    // proxy. The eslint `no-restricted-syntax` rule enforces the JSX side at
    // build-time; this assertion guards behaviour at runtime.
    expect(sendBtn.className).toMatch(/rounded-md/);
  });

  it("clear button empties the conversation and disables itself when there are no turns", async () => {
    installFetch({
      "/oracle/history": () => ({
        ok: true,
        status: 200,
        json: async () => ({
          conversation_id: CONVO_ID,
          turns: [
            {
              id: TURN_ID,
              conversation_id: CONVO_ID,
              role: "oracle",
              content: "Hello there.",
              tokens_used: 10,
              created_at: "2026-05-25T00:00:00Z",
            },
          ],
        }),
      }),
    });

    render(<OracleChat engagementId="e1" />);
    const user = userEvent.setup();
    await openPanel(user);
    await screen.findByText(/hello there/i);

    const clearBtn = screen.getByRole("button", { name: /clear/i });
    expect((clearBtn as HTMLButtonElement).disabled).toBe(false);
    await user.click(clearBtn);

    await waitFor(() => {
      expect(screen.queryByText(/hello there/i)).toBeNull();
    });
    expect((screen.getByRole("button", { name: /clear/i }) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });
});
