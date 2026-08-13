import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { SlackChannelMapping, SlackPendingChannel } from "@/lib/internal/slack-intake-cp";

import { SlackChannelsCard } from "./SlackChannelsCard.client";

function mkMapping(overrides: Partial<SlackChannelMapping> = {}): SlackChannelMapping {
  return {
    id: "m1",
    tenant_id: "t1",
    channel_id: "C123",
    channel_name: "proj-rollout",
    engagement_id: "e1",
    created_by: null,
    created_at: "2026-08-13T09:00:00Z",
    revoked_at: null,
    ...overrides,
  };
}

function mkPending(overrides: Partial<SlackPendingChannel> = {}): SlackPendingChannel {
  return {
    id: "p1",
    channel_id: "C456",
    channel_name: "proj-new",
    first_seen_at: "2026-08-13T10:00:00Z",
    ...overrides,
  };
}

type Call = { url: string; method: string; body?: unknown };

function mockFetch(handlers: {
  mappings?: SlackChannelMapping[];
  pending?: SlackPendingChannel[];
  engagements?: Array<{ id: string; name: string }>;
}): { calls: Call[] } {
  const calls: Call[] = [];
  const fetchMock = vi.fn((url: string, init?: { method?: string; body?: string }) => {
    const method = init?.method ?? "GET";
    const parsedBody = init?.body ? JSON.parse(init.body) : undefined;
    calls.push({ url, method, body: parsedBody });

    if (method === "GET" && url === "/api/bff/tenant/slack-channels") {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            mappings: handlers.mappings ?? [],
            pending: handlers.pending ?? [],
          }),
      });
    }
    if (method === "GET" && url === "/api/bff/engagements") {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            engagements: handlers.engagements ?? [{ id: "e1", name: "Acme rollout" }],
          }),
      });
    }
    if (method === "POST" && url === "/api/bff/tenant/slack-channels") {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ mapping: mkMapping() }),
      });
    }
    if (method === "POST" && url.endsWith("/revoke")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ mapping: mkMapping({ revoked_at: "2026-08-13T11:00:00Z" }) }),
      });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls };
}

describe("SlackChannelsCard", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("lists mapped channels with their engagement name and a revoke action", async () => {
    const { calls } = mockFetch({ mappings: [mkMapping()] });
    render(<SlackChannelsCard />);
    expect(await screen.findByText("#proj-rollout")).toBeInTheDocument();
    expect(screen.getByText("→ Acme rollout")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Revoke" }));
    await waitFor(() => {
      expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/m1/revoke"))).toBe(true);
    });
  });

  it("offers pending channels for mapping and posts the picked engagement", async () => {
    const { calls } = mockFetch({ pending: [mkPending()] });
    render(<SlackChannelsCard />);
    expect(await screen.findByText("#proj-new")).toBeInTheDocument();

    const picker = screen.getByLabelText("Engagement for proj-new");
    await userEvent.selectOptions(picker, "e1");
    await userEvent.click(screen.getAllByRole("button", { name: "Map channel" })[0]!);

    await waitFor(() => {
      const post = calls.find(
        (c) => c.method === "POST" && c.url === "/api/bff/tenant/slack-channels",
      );
      expect(post?.body).toEqual({
        channel_id: "C456",
        channel_name: "proj-new",
        engagement_id: "e1",
      });
    });
  });

  it("shows the empty state when nothing is mapped", async () => {
    mockFetch({});
    render(<SlackChannelsCard />);
    expect(await screen.findByText(/No channels are mapped yet/)).toBeInTheDocument();
  });
});
