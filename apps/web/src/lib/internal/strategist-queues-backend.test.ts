import { afterEach, describe, expect, it, vi } from "vitest";

import {
  strategistQueuesCpMisconfiguredForTenant,
  strategistQueuesShouldRejectMemoryFallback,
  strategistQueuesUseControlPlane,
} from "./strategist-queues-backend";

describe("strategist-queues-backend", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("strategistQueuesUseControlPlane is true only for cp", () => {
    vi.stubEnv("DEPLOYAI_STRATEGIST_QUEUES_BACKEND", "cp");
    expect(strategistQueuesUseControlPlane()).toBe(true);
    vi.stubEnv("DEPLOYAI_STRATEGIST_QUEUES_BACKEND", "memory");
    expect(strategistQueuesUseControlPlane()).toBe(false);
  });

  it("strategistQueuesCpMisconfiguredForTenant when url or key missing", () => {
    vi.stubEnv("DEPLOYAI_STRATEGIST_QUEUES_BACKEND", "cp");
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://localhost:8000");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "");
    expect(strategistQueuesCpMisconfiguredForTenant("550e8400-e29b-41d4-a716-446655440000")).toBe(true);
  });

  it("strategistQueuesShouldRejectMemoryFallback in production unless escape hatch", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("DEPLOYAI_STRATEGIST_QUEUES_BACKEND", "cp");
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "k");
    expect(strategistQueuesShouldRejectMemoryFallback("550e8400-e29b-41d4-a716-446655440000")).toBe(true);
    vi.stubEnv("DEPLOYAI_STRATEGIST_QUEUE_CP_ALLOW_MEMORY_FALLBACK", "1");
    expect(strategistQueuesShouldRejectMemoryFallback("550e8400-e29b-41d4-a716-446655440000")).toBe(false);
  });

  it("strategistQueuesShouldRejectMemoryFallback is false in development", () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("DEPLOYAI_STRATEGIST_QUEUES_BACKEND", "cp");
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "");
    expect(strategistQueuesShouldRejectMemoryFallback("550e8400-e29b-41d4-a716-446655440000")).toBe(false);
  });
});
