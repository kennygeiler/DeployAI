import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EngagementDetail } from "./EngagementDetail.client";

const ENGAGEMENT = {
  id: "e1",
  tenant_id: "t1",
  name: "NYC DOT LiDAR",
  customer_account: "NYC DOT",
  current_phase: "P5_pilot",
  status: "active",
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-10T00:00:00Z",
};

describe("EngagementDetail", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the engagement with its team and log", async () => {
    const fetchMock = vi.fn();
    fetchMock.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          engagement: ENGAGEMENT,
          members: [
            {
              id: "m1",
              engagement_id: "e1",
              user_id: "u1",
              role: "fde",
              created_at: "2026-05-02T00:00:00Z",
            },
          ],
          log: [
            {
              id: "l1",
              engagement_id: "e1",
              entry_kind: "decision",
              body: "Chose a phased rollout",
              author: "Dana",
              author_role: "deployment_strategist",
              created_at: "2026-05-09T00:00:00Z",
            },
          ],
        }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<EngagementDetail engagementId="e1" />);

    await waitFor(() => screen.getByText("NYC DOT LiDAR"));
    expect(screen.getByText("Phase: Pilot")).toBeTruthy();
    expect(screen.getByText("u1")).toBeTruthy();
    expect(screen.getByText("Chose a phased rollout")).toBeTruthy();
  });

  it("shows the BFF error description when the request fails", async () => {
    const fetchMock = vi.fn();
    fetchMock.mockResolvedValue({
      ok: false,
      text: () =>
        Promise.resolve(JSON.stringify({ userMessage: "That engagement was not found." })),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<EngagementDetail engagementId="missing" />);

    await waitFor(() => screen.getByText("That engagement was not found."));
  });

  it("assigns a member through the membership form", async () => {
    const calls: Array<{ url: string; method: string; body: string }> = [];
    const fetchMock = vi.fn((url: string, init?: { method?: string; body?: unknown }) => {
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: typeof init?.body === "string" ? init.body : "" });
      if (method === "POST") {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ member: {} }) });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ engagement: ENGAGEMENT, members: [], log: [] }),
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<EngagementDetail engagementId="e1" />);

    await waitFor(() => screen.getByText("NYC DOT LiDAR"));
    await user.type(screen.getByLabelText("User ID"), "user-9");
    await user.selectOptions(screen.getByLabelText("Role"), "biz_dev");
    await user.click(screen.getByRole("button", { name: "Assign" }));

    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const posted = calls.find((c) => c.method === "POST");
    expect(posted?.url).toContain("/api/bff/engagements/e1/members");
    expect(posted?.body).toContain("user-9");
    expect(posted?.body).toContain("biz_dev");
  });

  it("removes a member via the per-row remove button", async () => {
    const calls: Array<{ url: string; method: string }> = [];
    const fetchMock = vi.fn((url: string, init?: { method?: string }) => {
      const method = init?.method ?? "GET";
      calls.push({ url, method });
      if (method === "DELETE") {
        return Promise.resolve({ ok: true });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            engagement: ENGAGEMENT,
            members: [
              {
                id: "m1",
                engagement_id: "e1",
                user_id: "u1",
                role: "fde",
                created_at: "2026-05-02T00:00:00Z",
              },
            ],
            log: [],
          }),
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<EngagementDetail engagementId="e1" />);

    await waitFor(() => screen.getByRole("button", { name: "Remove" }));
    await user.click(screen.getByRole("button", { name: "Remove" }));

    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
    const deleted = calls.find((c) => c.method === "DELETE");
    expect(deleted?.url).toContain("/api/bff/engagements/e1/members/m1");
  });

  it("breaks log activity down by role and filters via the role lens", async () => {
    const fetchMock = vi.fn();
    fetchMock.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          engagement: ENGAGEMENT,
          members: [],
          log: [
            {
              id: "l1",
              engagement_id: "e1",
              entry_kind: "risk",
              body: "Sensor drift on the north corridor",
              author: "u1",
              author_role: "fde",
              created_at: "2026-05-09T00:00:00Z",
            },
            {
              id: "l2",
              engagement_id: "e1",
              entry_kind: "decision",
              body: "Approved the phased rollout",
              author: "u2",
              author_role: "deployment_strategist",
              created_at: "2026-05-10T00:00:00Z",
            },
          ],
        }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<EngagementDetail engagementId="e1" />);

    await waitFor(() => screen.getByText("Sensor drift on the north corridor"));
    // Both entries visible under the default "All roles" lens.
    expect(screen.getByText("Approved the phased rollout")).toBeTruthy();
    // biz_dev logged nothing — the coverage gap is surfaced.
    expect(screen.getByText(/No log activity yet from:.*Business development/)).toBeTruthy();

    // Narrowing the lens to FDE hides the strategist's entry.
    await user.selectOptions(screen.getByLabelText("Role lens"), "fde");
    expect(screen.getByText("Sensor drift on the north corridor")).toBeTruthy();
    expect(screen.queryByText("Approved the phased rollout")).toBeNull();
  });
});
