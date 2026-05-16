import { describe, expect, it, vi } from "vitest";

import * as strategistLocalDate from "@/lib/internal/strategist-local-date";
import { actionQueueRowMatchesDueWindow } from "./phase-tracking-due-window";

describe("actionQueueRowMatchesDueWindow", () => {
  const today = "2026-04-24";

  it("all passes any due", () => {
    expect(actionQueueRowMatchesDueWindow("2026-01-01", "all", today)).toBe(true);
  });

  it("today only matches reference day", () => {
    expect(actionQueueRowMatchesDueWindow(today, "today", today)).toBe(true);
    expect(actionQueueRowMatchesDueWindow("2026-04-25", "today", today)).toBe(false);
  });

  it("overdue is strictly before mock today", () => {
    expect(actionQueueRowMatchesDueWindow("2026-04-20", "overdue", today)).toBe(true);
    expect(actionQueueRowMatchesDueWindow(today, "overdue", today)).toBe(false);
  });

  it("next7 includes today through today+6", () => {
    expect(actionQueueRowMatchesDueWindow(today, "next7", today)).toBe(true);
    expect(actionQueueRowMatchesDueWindow("2026-04-30", "next7", today)).toBe(true);
    expect(actionQueueRowMatchesDueWindow("2026-05-01", "next7", today)).toBe(false);
    expect(actionQueueRowMatchesDueWindow("2026-04-19", "next7", today)).toBe(false);
  });

  it("falls back to strategist server local day when reference day is undefined or non-ISO", () => {
    vi.spyOn(strategistLocalDate, "getStrategistLocalDateForServer").mockReturnValue(today);
    expect(
      actionQueueRowMatchesDueWindow("2026-04-30", "next7", undefined as unknown as string),
    ).toBe(true);
    expect(actionQueueRowMatchesDueWindow("2026-04-30", "next7", "not-a-date")).toBe(true);
    vi.restoreAllMocks();
  });
});
