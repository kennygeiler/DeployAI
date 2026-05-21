import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EngagementSelector } from "./EngagementSelector.client";

function stubFetch(engagements: Array<{ id: string; name: string }>) {
  const fetchMock = vi.fn();
  fetchMock.mockResolvedValue({
    ok: true,
    json: () => Promise.resolve({ engagements }),
  });
  vi.stubGlobal("fetch", fetchMock);
}

describe("EngagementSelector", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the tenant's engagements plus an All option", async () => {
    stubFetch([
      { id: "e1", name: "NYC DOT LiDAR" },
      { id: "e2", name: "Acme rollout" },
    ]);
    render(<EngagementSelector value={undefined} onChange={vi.fn()} />);

    expect(screen.getByRole("option", { name: "All engagements" })).toBeTruthy();
    await waitFor(() => screen.getByRole("option", { name: "NYC DOT LiDAR" }));
    expect(screen.getByRole("option", { name: "Acme rollout" })).toBeTruthy();
  });

  it("reports the picked engagement id via onChange", async () => {
    stubFetch([{ id: "e1", name: "NYC DOT LiDAR" }]);
    const onChange = vi.fn<(id: string | undefined) => void>();
    const user = userEvent.setup();
    render(<EngagementSelector value={undefined} onChange={onChange} />);

    await waitFor(() => screen.getByRole("option", { name: "NYC DOT LiDAR" }));
    await user.selectOptions(screen.getByLabelText("Engagement"), "e1");

    expect(onChange).toHaveBeenCalledWith("e1");
  });
});
