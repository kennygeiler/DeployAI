import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiKeyList } from "@/components/settings/ApiKeyList.client";

type FetchCall = { url: string; method: string; body?: unknown };

const ENG_A = { id: "eng-aaaa", name: "BlueState" };

function mockClipboard() {
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText: vi.fn(() => Promise.resolve()) },
    writable: true,
    configurable: true,
  });
}

function mockFetch(
  routes: {
    onMint?: () => unknown;
    onRevoke?: () => unknown;
    onListKeys?: () => Array<Record<string, unknown>>;
  } = {},
) {
  const calls: FetchCall[] = [];
  let listCallCount = 0;
  const fetchMock = vi.fn((url: string, init?: { method?: string; body?: string }) => {
    const method = init?.method ?? "GET";
    const parsedBody = init?.body ? JSON.parse(init.body) : undefined;
    calls.push({ url, method, body: parsedBody });
    if (method === "GET" && url.endsWith("/api/bff/tenant/api-keys")) {
      listCallCount += 1;
      const keys = routes.onListKeys ? routes.onListKeys() : [];
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ api_keys: keys }) });
    }
    if (method === "GET" && url.endsWith("/api/bff/engagements")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ engagements: [ENG_A] }),
      });
    }
    if (method === "POST" && url.endsWith("/api/bff/tenant/api-keys")) {
      const payload = routes.onMint
        ? routes.onMint()
        : {
            api_key: {
              id: "key-1",
              tenant_id: "tt",
              engagement_id: (parsedBody as { engagement_id: string }).engagement_id,
              name: (parsedBody as { name: string }).name,
              scopes: ["read"],
              last_used_at: null,
              created_at: new Date().toISOString(),
              revoked_at: null,
            },
            raw_key: "mcp_live_abcdef0123456789abcdef0123456789abcdef0123456789",
          };
      return Promise.resolve({ ok: true, json: () => Promise.resolve(payload) });
    }
    if (method === "DELETE") {
      routes.onRevoke?.();
      return Promise.resolve({ ok: true, status: 204, json: () => Promise.resolve({}) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, listCallCount: () => listCallCount };
}

describe("ApiKeyList", () => {
  beforeEach(() => {
    mockClipboard();
    vi.stubGlobal("confirm", () => true);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders an empty state when no keys exist", async () => {
    mockFetch({ onListKeys: () => [] });
    render(<ApiKeyList />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    expect(screen.getByText("No api keys yet.")).toBeTruthy();
    expect(screen.getByRole("button", { name: /mint api key/i })).toBeTruthy();
  });

  it("opens the mint dialog and posts a mint request showing the raw key once", async () => {
    let mintedKey: Record<string, unknown> | null = null;
    const { calls } = mockFetch({
      onListKeys: () => (mintedKey ? [mintedKey] : []),
      onMint: () => {
        mintedKey = {
          id: "key-1",
          tenant_id: "tt",
          engagement_id: ENG_A.id,
          name: "bob",
          scopes: ["read"],
          last_used_at: null,
          created_at: new Date().toISOString(),
          revoked_at: null,
        };
        return {
          api_key: mintedKey,
          raw_key: "mcp_live_aaaaaaaaaaaaaaaabbbbbbbbbbbbbbbbccccccccccccccc",
        };
      },
    });
    const user = userEvent.setup();
    render(<ApiKeyList />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    await user.click(screen.getByRole("button", { name: /mint api key/i }));
    await user.type(screen.getByLabelText(/Name/i), "bob");
    await user.click(screen.getByRole("button", { name: /^mint$/i }));

    await waitFor(() => {
      expect(screen.getByTestId("raw-key-display")).toBeTruthy();
    });
    const raw = screen.getByTestId("raw-key-display").textContent;
    expect(raw?.startsWith("mcp_live_")).toBe(true);

    const post = calls.find((c) => c.method === "POST");
    expect(post?.url).toBe("/api/bff/tenant/api-keys");
    expect((post?.body as { name: string }).name).toBe("bob");
    expect((post?.body as { engagement_id: string }).engagement_id).toBe(ENG_A.id);
  });

  it("revokes a key on click and refreshes the list", async () => {
    let revoked = false;
    mockFetch({
      onListKeys: () => [
        {
          id: "key-active",
          tenant_id: "tt",
          engagement_id: ENG_A.id,
          name: "to-revoke",
          scopes: ["read"],
          last_used_at: null,
          created_at: new Date().toISOString(),
          revoked_at: revoked ? new Date().toISOString() : null,
        },
      ],
      onRevoke: () => {
        revoked = true;
      },
    });
    const user = userEvent.setup();
    render(<ApiKeyList />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    await user.click(screen.getByRole("button", { name: /revoke/i }));
    await waitFor(() => expect(screen.queryByText(/revoked:/)).toBeTruthy());
  });
});
