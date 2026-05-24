import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Webhook } from "@/lib/internal/webhooks-cp";

import { WebhooksForm } from "./WebhooksForm.client";

function mkWebhook(overrides: Partial<Webhook> = {}): Webhook {
  return {
    id: "w1",
    tenant_id: "t1",
    name: "ops",
    url: "https://example.com/hook",
    events: ["insight.created"],
    active: true,
    secret_masked: "abcd****wxyz",
    has_secret: true,
    created_at: "2026-05-23T12:00:00Z",
    updated_at: "2026-05-23T12:00:00Z",
    ...overrides,
  };
}

type Call = { url: string; method: string; body?: unknown };

function mockFetch(handlers: {
  listResponses?: Array<{ webhooks: Webhook[] }>;
  post?: (body: unknown) => unknown;
  put?: (body: unknown) => unknown;
  del?: () => unknown;
  deliveries?: () => unknown;
}): { calls: Call[] } {
  const calls: Call[] = [];
  const listResponses = handlers.listResponses ?? [{ webhooks: [] }];
  let listIdx = 0;
  const fetchMock = vi.fn((url: string, init?: { method?: string; body?: string }) => {
    const method = init?.method ?? "GET";
    const parsedBody = init?.body ? JSON.parse(init.body) : undefined;
    calls.push({ url, method, body: parsedBody });

    if (method === "GET" && url === "/api/bff/tenant/webhooks") {
      const resp = listResponses[Math.min(listIdx, listResponses.length - 1)];
      listIdx += 1;
      return Promise.resolve({ ok: true, json: () => Promise.resolve(resp) });
    }
    if (method === "POST" && url === "/api/bff/tenant/webhooks") {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(handlers.post ? handlers.post(parsedBody) : {}),
      });
    }
    if (method === "PUT" && url.startsWith("/api/bff/tenant/webhooks/")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(handlers.put ? handlers.put(parsedBody) : {}),
      });
    }
    if (method === "DELETE" && url.startsWith("/api/bff/tenant/webhooks/")) {
      return Promise.resolve({
        ok: true,
        status: 204,
        json: () => Promise.resolve(handlers.del ? handlers.del() : {}),
      });
    }
    if (method === "GET" && url.includes("/deliveries")) {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve(handlers.deliveries ? handlers.deliveries() : { deliveries: [] }),
      });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls };
}

describe("WebhooksForm", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders empty state when there are no webhooks", async () => {
    mockFetch({ listResponses: [{ webhooks: [] }] });
    render(<WebhooksForm />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    expect(screen.getByText("No webhooks yet.")).toBeTruthy();
    expect(screen.getByLabelText("Name")).toBeTruthy();
    expect(screen.getByLabelText("URL")).toBeTruthy();
    expect(screen.getByText("insight.created")).toBeTruthy();
  });

  it("renders an existing webhook with masked secret", async () => {
    mockFetch({ listResponses: [{ webhooks: [mkWebhook()] }] });
    render(<WebhooksForm />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    expect(screen.getByText("ops")).toBeTruthy();
    expect(screen.getByText(/abcd\*\*\*\*wxyz/)).toBeTruthy();
    expect(screen.getByText("https://example.com/hook")).toBeTruthy();
  });

  it("creates a webhook and flashes the returned secret once", async () => {
    const { calls } = mockFetch({
      listResponses: [
        { webhooks: [] },
        {
          webhooks: [mkWebhook({ id: "new", name: "new-hook", url: "https://x.example/h" })],
        },
      ],
      post: () => ({
        webhook: {
          ...mkWebhook({ id: "new", name: "new-hook", url: "https://x.example/h" }),
          secret: "PLAINTEXT-SECRET-VALUE-12345",
        },
      }),
    });
    render(<WebhooksForm />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Name"), "new-hook");
    await user.type(screen.getByLabelText("URL"), "https://x.example/h");
    await user.click(screen.getByLabelText("insight.created"));
    await user.click(screen.getByRole("button", { name: /create webhook/i }));

    await waitFor(() => expect(screen.queryByText(/PLAINTEXT-SECRET-VALUE-12345/)).toBeTruthy());
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.body).toEqual({
      name: "new-hook",
      url: "https://x.example/h",
      events: ["insight.created"],
    });
  });

  it("deletes a webhook via the row button", async () => {
    const { calls } = mockFetch({
      listResponses: [{ webhooks: [mkWebhook()] }, { webhooks: [] }],
    });
    render(<WebhooksForm />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /delete/i }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
    const del = calls.find((c) => c.method === "DELETE")!;
    expect(del.url).toBe("/api/bff/tenant/webhooks/w1");
  });
});
