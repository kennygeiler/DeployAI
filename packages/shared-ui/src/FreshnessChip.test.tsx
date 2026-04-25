import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { FreshnessChip } from "./FreshnessChip";

describe("FreshnessChip", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    cleanup();
  });

  it("shows unavailable when there is no sync time", () => {
    const t = Date.parse("2026-04-25T12:00:00.000Z");
    vi.setSystemTime(t);
    render(<FreshnessChip lastSyncedAt={null} tickMs={60_000} />);
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    expect(document.querySelector("[data-freshness='unavailable']")).toBeInTheDocument();
  });

  it("renders fresh when age is within freshMaxMs", () => {
    const t = Date.parse("2026-04-25T12:00:00.000Z");
    vi.setSystemTime(t);
    render(
      <FreshnessChip
        lastSyncedAt={t - 3_000}
        thresholdsMs={{ freshMaxMs: 10_000, staleMaxMs: 60_000 }}
        tickMs={60_000}
      />,
    );
    expect(document.querySelector("[data-freshness='fresh']")).toBeInTheDocument();
    expect(screen.getByText(/Synced 3s ago/i)).toBeInTheDocument();
  });

  it("renders very-stale when age is past staleMaxMs", () => {
    const t = Date.parse("2026-04-25T12:00:00.000Z");
    vi.setSystemTime(t);
    render(
      <FreshnessChip
        lastSyncedAt={t - 500_000}
        thresholdsMs={{ freshMaxMs: 10_000, staleMaxMs: 60_000 }}
        tickMs={60_000}
      />,
    );
    expect(document.querySelector("[data-freshness='very-stale']")).toBeInTheDocument();
  });
});
