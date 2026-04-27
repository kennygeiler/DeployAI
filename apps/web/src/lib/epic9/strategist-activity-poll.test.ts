import { describe, expect, it } from "vitest";

import { strategistActivityPollMsFromEnv } from "./strategist-activity-poll";

describe("strategistActivityPollMsFromEnv (Epic 9.1)", () => {
  it("defaults empty to 30s", () => {
    expect(strategistActivityPollMsFromEnv(undefined)).toBe(30_000);
    expect(strategistActivityPollMsFromEnv("")).toBe(30_000);
    expect(strategistActivityPollMsFromEnv("   ")).toBe(30_000);
  });

  it("clamps to max 30s", () => {
    expect(strategistActivityPollMsFromEnv("120000")).toBe(30_000);
  });

  it("clamps invalid low to default", () => {
    expect(strategistActivityPollMsFromEnv("4999")).toBe(30_000);
    expect(strategistActivityPollMsFromEnv("not-a-number")).toBe(30_000);
  });

  it("accepts mid-range values", () => {
    expect(strategistActivityPollMsFromEnv("10000")).toBe(10_000);
    expect(strategistActivityPollMsFromEnv("30000")).toBe(30_000);
  });
});
