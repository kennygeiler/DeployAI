import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StrategistNav } from "@/components/chrome/StrategistNav";

vi.mock("next/navigation", () => ({
  usePathname: () => "/engagements",
}));

function setDemoCookie(on: boolean) {
  document.cookie = on ? "demo_tour=1; path=/" : "demo_tour=; path=/; max-age=0";
}

describe("StrategistNav admin links", () => {
  afterEach(() => {
    setDemoCookie(false);
    vi.restoreAllMocks();
  });

  it("shows the admin telemetry links for regular sessions", () => {
    setDemoCookie(false);
    render(<StrategistNav />);
    expect(screen.getByTitle("Admin · MCP activity")).toBeInTheDocument();
    expect(screen.getByTitle("Admin · Agent Kenny dashboard")).toBeInTheDocument();
  });

  it("hides the admin links for demo-guest sessions (demo_tour cookie)", async () => {
    // demo_guest holds canonical:read only — the /admin pages 403 at the
    // middleware, so their links must not render as dead ends.
    setDemoCookie(true);
    render(<StrategistNav />);
    await waitFor(() => {
      expect(screen.queryByTitle("Admin · MCP activity")).not.toBeInTheDocument();
    });
    expect(screen.queryByTitle("Admin · Agent Kenny dashboard")).not.toBeInTheDocument();
    // Non-admin items stay.
    expect(screen.getByTitle("Engagements")).toBeInTheDocument();
    expect(screen.getByTitle("Overview")).toBeInTheDocument();
  });
});
