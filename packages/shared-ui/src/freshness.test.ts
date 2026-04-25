import { describe, expect, it } from "vitest";

import { FRESHNESS_NFR5_MS, formatSyncAge, freshnessStateForAge } from "./freshness";

describe("freshnessStateForAge", () => {
  it("classifies by thresholds", () => {
    const t = { freshMaxMs: 100, staleMaxMs: 200 };
    expect(freshnessStateForAge(50, t)).toBe("fresh");
    expect(freshnessStateForAge(150, t)).toBe("stale");
    expect(freshnessStateForAge(250, t)).toBe("very-stale");
  });

  it("returns unavailable for null age", () => {
    expect(freshnessStateForAge(null, { freshMaxMs: 1, staleMaxMs: 2 })).toBe("unavailable");
  });

  it("treats negative or non-finite age as fresh (clock skew)", () => {
    const t = FRESHNESS_NFR5_MS.digest;
    expect(freshnessStateForAge(-1, t)).toBe("fresh");
    expect(freshnessStateForAge(Number.NaN, t)).toBe("fresh");
  });
});

describe("formatSyncAge", () => {
  it("formats seconds and minutes", () => {
    expect(formatSyncAge(45_000)).toBe("45s ago");
    expect(formatSyncAge(3 * 60_000)).toBe("3m ago");
  });

  it("returns em dash for null", () => {
    expect(formatSyncAge(null)).toBe("—");
  });
});
