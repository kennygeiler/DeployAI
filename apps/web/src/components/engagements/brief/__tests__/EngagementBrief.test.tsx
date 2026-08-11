import { render, screen, waitFor, within } from "@testing-library/react";
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

import { EngagementBrief } from "@/components/engagements/brief/EngagementBrief.client";

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

const SUMMARY = {
  engagement: {
    id: "e1",
    name: "NYC DOT LiDAR",
    customer_account: "NYC DOT",
    current_phase: "P5_pilot",
    status: "active",
    updated_at: "2026-05-10T00:00:00Z",
  },
  members: [
    { user_id: "u1", display_name: "Ada Lovelace", email: "ada@nycdot.gov", role: "fde" },
  ],
  counts: {
    stakeholders: 3,
    decisions: 2,
    risks_open: 1,
    commitments: 0,
    proposals_pending: 1,
    escalations_open: 2,
    disputes_open: 0,
  },
  recent_changes: [
    {
      occurred_at: "2026-08-10T09:00:00Z",
      kind: "risk_closed",
      title: "Risk closed: calibration slip",
      actor_display_name: "Ada Lovelace",
    },
    {
      occurred_at: "2026-08-09T15:00:00Z",
      kind: "decision_accepted",
      title: "Phase 2 rollout approved",
      actor_display_name: null,
    },
  ],
};

function mkNode(id: string, node_type: string, title: string, status: string | null = null) {
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
  };
}

type MockOptions = {
  summaryOk?: boolean;
  detail?: Record<string, unknown>;
};

function stubFetch(opts: MockOptions = {}) {
  const calls: Array<{ url: string; method: string; body: string }> = [];
  const detail = opts.detail ?? { engagement: ENGAGEMENT, members: [] };
  const fetchMock = vi.fn((url: string, init?: { method?: string; body?: unknown }) => {
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: typeof init?.body === "string" ? init.body : "" });
    if (url.includes("/summary")) {
      if (opts.summaryOk === false) {
        return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve(SUMMARY) });
    }
    if (url.includes("/members") && method === "POST") {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ member: {} }) });
    }
    if (url.includes("/members/") && method === "DELETE") {
      return Promise.resolve({ ok: true });
    }
    if (url.includes("/member-roles")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ builtin: [], custom: [] }),
      });
    }
    if (url.includes("/insights")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ insights: [] }) });
    }
    if (url.includes("/recommendations")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ recommendations: [] }) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve(detail) });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

describe("EngagementBrief", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders header, count chips, and the delta digest from the summary", async () => {
    stubFetch();
    render(<EngagementBrief engagementId="e1" />);

    await waitFor(() => screen.getByText("NYC DOT LiDAR"));
    expect(screen.getByText("Phase: Pilot")).toBeTruthy();

    const chips = screen.getByTestId("brief-count-chips");
    expect(chips.textContent).toContain("stakeholders");
    expect(chips.textContent).toContain("pending proposals");

    const digest = await screen.findByTestId("delta-digest");
    // Grouped by bucket with human titles — the duplicated kind prefix is gone.
    expect(within(digest).getByText("calibration slip")).toBeTruthy();
    expect(within(digest).getByText("Phase 2 rollout approved")).toBeTruthy();
    expect(digest.textContent).toContain("Risks");
    expect(digest.textContent).toContain("Decisions");
    expect(digest.textContent).not.toContain("risk_closed");
  });

  it("shows the needs-you queue with escalation links from summary counts", async () => {
    stubFetch();
    render(<EngagementBrief engagementId="e1" />);
    const needsYou = await screen.findByTestId("needs-you");
    await waitFor(() =>
      expect(within(needsYou).getByTestId("needs-you-review-links")).toBeTruthy(),
    );
    expect(needsYou.textContent).toContain("open escalations");
  });

  it("degrades to the detail payload when the summary endpoint 404s", async () => {
    stubFetch({ summaryOk: false });
    render(<EngagementBrief engagementId="e1" />);
    // Header still renders from the detail aggregate.
    await waitFor(() => screen.getByText("NYC DOT LiDAR"));
    expect(screen.getByText("Phase: Pilot")).toBeTruthy();
  });

  it("renders narrative cards with empty states (U9)", async () => {
    stubFetch({
      detail: {
        engagement: ENGAGEMENT,
        members: [],
        matrix: {
          nodes: [mkNode("n1", "risk", "Calibration slip", "open")],
          edges: [],
        },
      },
    });
    render(<EngagementBrief engagementId="e1" />);
    await waitFor(() => screen.getByTestId("brief-card-risks"));
    expect(within(screen.getByTestId("brief-card-risks")).getByText("Calibration slip")).toBeTruthy();
    // Empty states explain how data arrives.
    expect(screen.getByTestId("brief-card-commitments").textContent).toContain(
      "No commitments tracked yet",
    );
    expect(screen.getByTestId("brief-card-people").textContent).toContain(
      "No stakeholders mapped yet",
    );
  });

  it("manages members in the People tab (assign + remove)", async () => {
    const calls = stubFetch({
      detail: {
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
      },
    });
    const user = userEvent.setup();
    render(<EngagementBrief engagementId="e1" />);
    await waitFor(() => screen.getByText("NYC DOT LiDAR"));

    await user.click(screen.getByRole("tab", { name: "People" }));
    // The member renders by display name (from summary identity), not UUID.
    await waitFor(() => screen.getByText("Ada Lovelace"));

    await user.type(screen.getByLabelText("Email"), "new.user@example.com");
    await user.click(screen.getByRole("button", { name: "Assign" }));
    await waitFor(() =>
      expect(
        calls.some((c) => c.method === "POST" && c.url.includes("/api/bff/engagements/e1/members")),
      ).toBe(true),
    );

    await user.click(screen.getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
    const deleted = calls.find((c) => c.method === "DELETE");
    expect(deleted?.url).toContain("/api/bff/engagements/e1/members/m1");
  });

  it("renders the matrix table with edges in the Graph tab", async () => {
    stubFetch({
      detail: {
        engagement: ENGAGEMENT,
        members: [],
        matrix: {
          nodes: [
            mkNode("n1", "system", "LiDAR ingest"),
            mkNode("n2", "risk", "Calibration slip", "open"),
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
      },
    });
    render(<EngagementBrief engagementId="e1" />);
    await waitFor(() => screen.getByText("Systems"));
    expect(screen.getByText("threatens → LiDAR ingest")).toBeTruthy();
    // The matrix-capture form stays wired into the Graph tab.
    expect(screen.getByText("Add to the matrix")).toBeTruthy();
  });
});
