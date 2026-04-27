import { afterEach, describe, expect, it, vi } from "vitest";

import { getStrategistLocalDateForServer } from "./strategist-local-date";

describe("getStrategistLocalDateForServer", () => {
  const origDemo = process.env.STRATEGIST_DEMO_TODAY;
  const origTz = process.env.STRATEGIST_LOCAL_TZ;

  afterEach(() => {
    if (origDemo === undefined) {
      delete process.env.STRATEGIST_DEMO_TODAY;
    } else {
      process.env.STRATEGIST_DEMO_TODAY = origDemo;
    }
    if (origTz === undefined) {
      delete process.env.STRATEGIST_LOCAL_TZ;
    } else {
      process.env.STRATEGIST_LOCAL_TZ = origTz;
    }
  });

  it("uses STRATEGIST_DEMO_TODAY when set to YYYY-MM-DD", () => {
    process.env.STRATEGIST_DEMO_TODAY = "2026-04-24";
    delete process.env.STRATEGIST_LOCAL_TZ;
    expect(getStrategistLocalDateForServer()).toBe("2026-04-24");
  });

  it("formats a fixed instant in America/New_York as strategist-local", () => {
    delete process.env.STRATEGIST_DEMO_TODAY;
    process.env.STRATEGIST_LOCAL_TZ = "America/New_York";
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-15T19:00:00.000Z"));
    try {
      expect(getStrategistLocalDateForServer()).toBe("2026-07-15");
    } finally {
      vi.useRealTimers();
    }
  });
});
