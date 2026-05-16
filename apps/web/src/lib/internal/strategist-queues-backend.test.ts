import { afterEach, describe, expect, it, vi } from "vitest";

import { strategistQueuesCpMisconfiguredForTenant } from "@/lib/internal/strategist-queues-backend";

describe("strategist-queues-backend (CP-only)", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("strategistQueuesCpMisconfiguredForTenant is false when no tenant id", () => {
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://localhost:8000");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "k");
    expect(strategistQueuesCpMisconfiguredForTenant("")).toBe(false);
    expect(strategistQueuesCpMisconfiguredForTenant(null)).toBe(false);
  });

  it("strategistQueuesCpMisconfiguredForTenant is true when tenant set but CP URL missing", () => {
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "k");
    expect(strategistQueuesCpMisconfiguredForTenant("550e8400-e29b-41d4-a716-446655440000")).toBe(
      true,
    );
  });

  it("strategistQueuesCpMisconfiguredForTenant is true when internal key missing", () => {
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://localhost:8000");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "");
    expect(strategistQueuesCpMisconfiguredForTenant("550e8400-e29b-41d4-a716-446655440000")).toBe(
      true,
    );
  });

  it("strategistQueuesCpMisconfiguredForTenant is false when both env vars present", () => {
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://localhost:8000");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "secret");
    expect(strategistQueuesCpMisconfiguredForTenant("550e8400-e29b-41d4-a716-446655440000")).toBe(
      false,
    );
  });
});
