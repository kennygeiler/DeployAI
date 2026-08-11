import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EngagementPortfolio } from "./EngagementPortfolio.client";

describe("EngagementPortfolio", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the team's engagements with a readable phase and status", async () => {
    const fetchMock = vi.fn();
    fetchMock.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          engagements: [
            {
              id: "e1",
              tenant_id: "t1",
              name: "NYC DOT LiDAR",
              customer_account: "NYC DOT",
              current_phase: "P5_pilot",
              status: "active",
              created_at: "2026-05-01T00:00:00Z",
              updated_at: "2026-05-10T00:00:00Z",
            },
          ],
        }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<EngagementPortfolio />);

    await waitFor(() => screen.getByText("NYC DOT LiDAR"));
    expect(screen.getByText("Pilot")).toBeTruthy();
    expect(screen.getByText("active")).toBeTruthy();
  });

  it("ranks rows by attention_score and shows needs-attention chips (U7)", async () => {
    const base = {
      tenant_id: "t1",
      customer_account: null,
      current_phase: "P5_pilot",
      status: "active",
      created_at: "2026-05-01T00:00:00Z",
      updated_at: "2026-05-10T00:00:00Z",
    };
    const fetchMock = vi.fn();
    fetchMock.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          engagements: [
            { ...base, id: "quiet", name: "Quiet Deal", attention_score: 0.1 },
            {
              ...base,
              id: "hot",
              name: "Hot Deal",
              attention_score: 9.5,
              needs_attention: {
                proposals_pending: 3,
                escalations_open: 1,
                days_since_last_event: 12,
              },
            },
          ],
        }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<EngagementPortfolio />);
    await waitFor(() => screen.getByText("Hot Deal"));

    const rows = screen.getAllByRole("row").slice(1); // skip the header row
    expect(rows[0]!.textContent).toContain("Hot Deal");
    expect(rows[1]!.textContent).toContain("Quiet Deal");

    const chips = screen.getByTestId("needs-attention-hot");
    expect(chips.textContent).toContain("3 proposals");
    expect(chips.textContent).toContain("1 escalation");
    expect(chips.textContent).toContain("12d silent");
  });

  it("degrades gracefully when needs_attention is absent (older CP)", async () => {
    const fetchMock = vi.fn();
    fetchMock.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          engagements: [
            {
              id: "e1",
              tenant_id: "t1",
              name: "Legacy Deal",
              customer_account: null,
              current_phase: "P2_discovery",
              status: "active",
              created_at: "2026-05-01T00:00:00Z",
              updated_at: "2026-05-10T00:00:00Z",
            },
          ],
        }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<EngagementPortfolio />);
    await waitFor(() => screen.getByText("Legacy Deal"));
    // The needs-attention cell falls back to a dash (customer is also "—").
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.queryByTestId("needs-attention-e1")).toBeNull();
  });
});
