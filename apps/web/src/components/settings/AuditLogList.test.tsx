import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuditLogList } from "./AuditLogList.client";

type AuditEventDTO = {
  id: string;
  tenant_id: string;
  actor_id: string;
  category: string;
  summary: string;
  detail: Record<string, unknown>;
  ref_id: string | null;
  created_at: string;
};

function mkEvent(overrides: Partial<AuditEventDTO> = {}): AuditEventDTO {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    tenant_id: "22222222-2222-2222-2222-222222222222",
    actor_id: "33333333-3333-3333-3333-333333333333",
    category: "override_added",
    summary: "Added override",
    detail: {},
    ref_id: null,
    created_at: "2026-05-23T12:00:00Z",
    ...overrides,
  };
}

type Call = { url: string; method: string; body?: unknown };

function mockFetch(handlers: { listResponses: Array<{ events: AuditEventDTO[] }> }): {
  calls: Call[];
} {
  const calls: Call[] = [];
  let idx = 0;
  const fetchMock = vi.fn((url: string, init?: { method?: string; body?: string }) => {
    const method = init?.method ?? "GET";
    calls.push({ url, method });
    if (method === "GET" && url.startsWith("/api/bff/tenant/audit")) {
      const resp = handlers.listResponses[Math.min(idx, handlers.listResponses.length - 1)];
      idx += 1;
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(resp) });
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls };
}

describe("AuditLogList", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders rows returned by the BFF", async () => {
    mockFetch({
      listResponses: [
        {
          events: [
            mkEvent({ id: "ev1", summary: "Override one", category: "override_added" }),
            mkEvent({ id: "ev2", summary: "Override two", category: "note_added" }),
          ],
        },
      ],
    });
    render(<AuditLogList />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    expect(screen.getByText("Override one")).toBeTruthy();
    expect(screen.getByText("Override two")).toBeTruthy();
    expect(screen.getByText("override_added")).toBeTruthy();
    expect(screen.getByText("note_added")).toBeTruthy();
  });

  it("refetches with actor + kind filters in the query string", async () => {
    const { calls } = mockFetch({
      listResponses: [{ events: [mkEvent()] }, { events: [] }],
    });
    render(<AuditLogList />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Actor (UUID)"), "44444444-4444-4444-4444-444444444444");
    await user.type(screen.getByLabelText("Kind"), "override_added");
    await waitFor(() => {
      const last = calls[calls.length - 1]!;
      expect(last.url).toContain("actor=44444444-4444-4444-4444-444444444444");
      expect(last.url).toContain("kind=override_added");
    });
  });

  it("paginates using the last row's created_at as the before cursor", async () => {
    const first = mkEvent({
      id: "a",
      summary: "first-summary",
      created_at: "2026-05-23T12:00:00Z",
    });
    const second = mkEvent({
      id: "b",
      summary: "second-summary",
      created_at: "2026-05-23T11:00:00Z",
    });
    const older = mkEvent({
      id: "c",
      summary: "older-summary",
      created_at: "2026-05-23T10:00:00Z",
    });

    const calls: Call[] = [];
    const fetchMock = vi.fn((url: string, init?: { method?: string; body?: string }) => {
      const method = init?.method ?? "GET";
      calls.push({ url, method });
      if (method === "GET" && url.startsWith("/api/bff/tenant/audit")) {
        const events = url.includes("before=") ? [older] : [first, second];
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ events }) });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<AuditLogList />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());

    const user = userEvent.setup();
    const pageSize = screen.getByLabelText("Page size") as HTMLInputElement;
    fireEvent.change(pageSize, { target: { value: "2" } });
    await waitFor(() => expect(screen.queryByText("first-summary")).not.toBeNull());
    await waitFor(() =>
      expect(
        (screen.getByRole("button", { name: /load older/i }) as HTMLButtonElement).disabled,
      ).toBe(false),
    );
    await user.click(screen.getByRole("button", { name: /load older/i }));

    await waitFor(() => expect(screen.queryByText("older-summary")).not.toBeNull());
    const last = calls[calls.length - 1]!;
    expect(last.url).toContain("before=2026-05-23T11%3A00%3A00Z");
  });
});
