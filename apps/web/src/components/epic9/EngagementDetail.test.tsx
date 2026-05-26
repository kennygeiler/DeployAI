import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: vi.fn(),
    push: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
  }),
  usePathname: () => "/engagements/e1",
  useSearchParams: () => new URLSearchParams(),
}));

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

  it("renders the engagement header and team", async () => {
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
        }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<EngagementDetail engagementId="e1" />);

    await waitFor(() => screen.getByText("NYC DOT LiDAR"));
    expect(screen.getByText("Phase: Pilot")).toBeTruthy();
    expect(screen.getByText("u1")).toBeTruthy();
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
        json: () => Promise.resolve({ engagement: ENGAGEMENT, members: [] }),
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<EngagementDetail engagementId="e1" />);

    await waitFor(() => screen.getByText("NYC DOT LiDAR"));
    await user.type(screen.getByLabelText("Email"), "new.user@example.com");
    await user.selectOptions(screen.getByLabelText("Role"), "biz_dev");
    await user.click(screen.getByRole("button", { name: "Assign" }));

    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const posted = calls.find((c) => c.method === "POST");
    expect(posted?.url).toContain("/api/bff/engagements/e1/members");
    expect(posted?.body).toContain("new.user@example.com");
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

  it("renders the deployment matrix grouped by node type with edges", async () => {
    const node = (id: string, node_type: string, title: string, status: string | null) => ({
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
    });
    const fetchMock = vi.fn();
    fetchMock.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          engagement: ENGAGEMENT,
          members: [],
          matrix: {
            nodes: [
              node("n1", "system", "LiDAR ingest", null),
              node("n2", "risk", "Calibration slip", "open"),
            ],
            edges: [
              {
                id: "ed1",
                engagement_id: "e1",
                edge_type: "threatens",
                from_node_id: "n2",
                to_node_id: "n1",
                attributes: {},
                evidence_event_ids: [],
                created_at: "2026-05-09T00:00:00Z",
                updated_at: "2026-05-09T00:00:00Z",
              },
            ],
          },
        }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<EngagementDetail engagementId="e1" />);

    await waitFor(() => screen.getByText("Systems"));
    expect(screen.getByText("Risks")).toBeTruthy();
    // The risk node shows its outgoing edge to the system it threatens.
    expect(screen.getByText("threatens → LiDAR ingest")).toBeTruthy();
    // The matrix-capture form is wired into the section.
    expect(screen.getByText("Add to the matrix")).toBeTruthy();
  });
});
