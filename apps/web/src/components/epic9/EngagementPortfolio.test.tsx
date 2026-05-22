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
});
