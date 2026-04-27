import { describe, expect, it } from "vitest";

import { PHASE_TRACKING_MOCK_TODAY, actionQueueRowMatchesDueWindow } from "./mock-digest";

describe("actionQueueRowMatchesDueWindow", () => {
  const today = PHASE_TRACKING_MOCK_TODAY;

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
});
