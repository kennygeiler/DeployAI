import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AskKennyGlobal } from "@/components/ask/AskKennyGlobal.client";
import { clearCachedFetchForTests } from "@/lib/hooks/useCachedFetch";

const ENGAGEMENTS = [
  {
    id: "e1",
    tenant_id: "t1",
    name: "NYC DOT LiDAR",
    customer_account: null,
    current_phase: "P5_pilot",
    status: "active",
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-10T00:00:00Z",
  },
  {
    id: "e2",
    tenant_id: "t1",
    name: "Boston Transit",
    customer_account: null,
    current_phase: "P2_discovery",
    status: "active",
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-10T00:00:00Z",
  },
];

function stubFetch(engagements: unknown[] = ENGAGEMENTS) {
  const calls: string[] = [];
  const fetchMock = vi.fn((url: string) => {
    calls.push(url);
    if (url === "/api/bff/engagements") {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ engagements }) });
    }
    if (url.includes("/oracle/history")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ conversation_id: null, turns: [] }),
      });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

describe("AskKennyGlobal (U10)", () => {
  beforeEach(() => {
    clearCachedFetchForTests();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows scope chips and mounts the chat for the first engagement", async () => {
    const calls = stubFetch();
    render(<AskKennyGlobal />);

    await waitFor(() => screen.getByTestId("ask-scope-e1"));
    expect(screen.getByTestId("ask-scope-e2")).toBeTruthy();
    const panel = await screen.findByTestId("oracle-chat-panel");
    expect(panel.getAttribute("data-variant")).toBe("embedded");
    // History loads for the scoped engagement only.
    await waitFor(() =>
      expect(calls.some((u) => u.includes("/engagements/e1/oracle/history"))).toBe(true),
    );
  });

  it("switches the chat scope when another chip is selected", async () => {
    const calls = stubFetch();
    const user = userEvent.setup();
    render(<AskKennyGlobal />);

    await waitFor(() => screen.getByTestId("ask-scope-e2"));
    await user.click(screen.getByTestId("ask-scope-e2"));
    await waitFor(() =>
      expect(calls.some((u) => u.includes("/engagements/e2/oracle/history"))).toBe(true),
    );
    expect(screen.getByTestId("ask-scope-e2").getAttribute("aria-pressed")).toBe("true");
  });

  it("renders the empty state when there are no engagements (U9)", async () => {
    stubFetch([]);
    render(<AskKennyGlobal />);
    await waitFor(() => screen.getByTestId("ask-empty"));
    expect(screen.getByTestId("ask-empty").textContent).toContain("onboarding wizard");
  });
});
