import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EngagementDetail } from "./EngagementDetail.client";

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
          engagement: {
            id: "e1",
            tenant_id: "t1",
            name: "NYC DOT LiDAR",
            customer_account: "NYC DOT",
            current_phase: "P5_pilot",
            status: "active",
            created_at: "2026-05-01T00:00:00Z",
            updated_at: "2026-05-10T00:00:00Z",
          },
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
              created_at: "2026-05-09T00:00:00Z",
            },
          ],
        }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<EngagementDetail engagementId="e1" />);

    await waitFor(() => screen.getByText("NYC DOT LiDAR"));
    expect(screen.getByText("Phase: Pilot")).toBeTruthy();
    expect(screen.getByText("Forward-deployed engineer")).toBeTruthy();
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
});
