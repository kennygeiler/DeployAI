import { afterEach, describe, expect, it, vi } from "vitest";

import { shouldAllowStrategistMeetingUrlDemo } from "./strategist-url-demo-policy";

describe("shouldAllowStrategistMeetingUrlDemo", () => {
  const originalFlag = process.env.NEXT_PUBLIC_DEPLOYAI_STRATEGIST_MEETING_URL_DEMO;

  afterEach(() => {
    vi.unstubAllEnvs();
    if (originalFlag === undefined) {
      delete process.env.NEXT_PUBLIC_DEPLOYAI_STRATEGIST_MEETING_URL_DEMO;
    } else {
      process.env.NEXT_PUBLIC_DEPLOYAI_STRATEGIST_MEETING_URL_DEMO = originalFlag;
    }
  });

  it("allows overlays outside production", () => {
    vi.stubEnv("NODE_ENV", "development");
    delete process.env.NEXT_PUBLIC_DEPLOYAI_STRATEGIST_MEETING_URL_DEMO;
    expect(shouldAllowStrategistMeetingUrlDemo()).toBe(true);
  });

  it("blocks overlays in production unless explicitly enabled", () => {
    vi.stubEnv("NODE_ENV", "production");
    delete process.env.NEXT_PUBLIC_DEPLOYAI_STRATEGIST_MEETING_URL_DEMO;
    expect(shouldAllowStrategistMeetingUrlDemo()).toBe(false);
  });

  it("allows overlays in production when public env is set", () => {
    vi.stubEnv("NODE_ENV", "production");
    process.env.NEXT_PUBLIC_DEPLOYAI_STRATEGIST_MEETING_URL_DEMO = "1";
    expect(shouldAllowStrategistMeetingUrlDemo()).toBe(true);
  });
});
