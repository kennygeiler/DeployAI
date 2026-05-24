import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AgentPromptsRead } from "@/lib/internal/agent-prompts-cp";

import { AgentPromptsForm } from "./AgentPromptsForm.client";

function mkPrompts(
  overrides: Partial<
    Record<keyof AgentPromptsRead["prompts"], { value: string; is_default: boolean }>
  > = {},
): AgentPromptsRead {
  return {
    prompts: {
      cartographer: { value: "default-carto", is_default: true },
      oracle: { value: "default-oracle", is_default: true },
      master_strategist: { value: "default-strategist", is_default: true },
      ...overrides,
    },
  };
}

type FetchCall = { url: string; method: string; body?: unknown };

function mockFetch(
  handlers: {
    get?: (() => unknown)[] | (() => unknown);
    put?: (body: unknown) => unknown;
    del?: () => unknown;
  } = {},
) {
  const calls: FetchCall[] = [];
  const getQueue = Array.isArray(handlers.get)
    ? [...handlers.get]
    : handlers.get
      ? [handlers.get]
      : [];
  const fetchMock = vi.fn((url: string, init?: { method?: string; body?: string }) => {
    const method = init?.method ?? "GET";
    const parsedBody = init?.body ? JSON.parse(init.body) : undefined;
    calls.push({ url, method, body: parsedBody });
    if (method === "GET") {
      const next = getQueue.shift() ?? (() => mkPrompts());
      return Promise.resolve({ ok: true, json: () => Promise.resolve(next()) });
    }
    if (method === "PUT" && handlers.put) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(handlers.put!(parsedBody)) });
    }
    if (method === "DELETE") {
      return Promise.resolve({
        ok: true,
        status: 204,
        json: () => Promise.resolve(handlers.del ? handlers.del() : {}),
      });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

describe("AgentPromptsForm", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders one textarea + reset disabled per agent when all defaults", async () => {
    mockFetch({ get: () => mkPrompts() });
    render(<AgentPromptsForm />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());

    for (const labelHint of [/Cartographer/, /Oracle/, /Master Strategist/]) {
      expect(screen.getByLabelText(labelHint)).toBeTruthy();
    }
    const resetButtons = screen.getAllByRole("button", { name: /reset to default/i });
    expect(resetButtons).toHaveLength(3);
    for (const btn of resetButtons) {
      expect((btn as HTMLButtonElement).disabled).toBe(true);
    }
    expect(screen.getAllByText(/Using baked-in default/)).toHaveLength(3);
  });

  it("PUTs the edited prompt for the agent the user saves", async () => {
    const calls = mockFetch({
      get: () => mkPrompts(),
      put: (body) => ({
        entry: { value: (body as { prompt_text: string }).prompt_text, is_default: false },
      }),
    });
    render(<AgentPromptsForm />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());

    const oracle = screen.getByLabelText(/Oracle/) as HTMLTextAreaElement;
    const user = userEvent.setup();
    await user.clear(oracle);
    await user.type(oracle, "my custom oracle");
    // The three Save buttons share text; pick the one inside the same form as oracle.
    const oracleForm = oracle.closest("form")!;
    await user.click(oracleForm.querySelector("button[type=submit]") as HTMLButtonElement);

    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    const put = calls.find((c) => c.method === "PUT")!;
    expect(put.url).toContain("/agent-prompts/oracle");
    expect((put.body as { prompt_text: string }).prompt_text).toBe("my custom oracle");
    // After save the override badge appears for that agent and Reset becomes enabled.
    await waitFor(() => {
      const overrideBadges = screen.getAllByText(/Custom override saved/);
      expect(overrideBadges.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("DELETEs and re-fetches when the user clicks Reset on an override", async () => {
    // First GET returns oracle as a custom override; second GET (post-reset) returns default.
    const calls = mockFetch({
      get: [
        () => mkPrompts({ oracle: { value: "custom oracle", is_default: false } }),
        () => mkPrompts(),
      ],
      del: () => ({}),
    });
    render(<AgentPromptsForm />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());

    const oracle = screen.getByLabelText(/Oracle/) as HTMLTextAreaElement;
    const oracleForm = oracle.closest("form")!;
    const resetButton = oracleForm.querySelector('button[type="button"]') as HTMLButtonElement;
    expect(resetButton.disabled).toBe(false);

    const user = userEvent.setup();
    await user.click(resetButton);

    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
    const del = calls.find((c) => c.method === "DELETE")!;
    expect(del.url).toContain("/agent-prompts/oracle");
    // After reset we reload and the textarea now holds the default value.
    await waitFor(() => expect(oracle.value).toBe("default-oracle"));
  });
});
