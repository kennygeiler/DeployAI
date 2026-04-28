import { describe, expect, it } from "vitest";

import {
  edgeAgentRegisterRequestSchema,
  edgeAgentRegisterResponseSchema,
} from "../src/edge-agent.js";

describe("edge-agent register contract", () => {
  it("accepts a minimal valid request", () => {
    const j = edgeAgentRegisterRequestSchema.parse({
      tenant_id: "00000000-0000-4000-8000-000000000001",
      device_id: "11111111-1111-4111-8111-111111111111",
      public_key_ed25519_b64: "AQIDBAUGBwgJCgsMDQ4PEA==",
    });
    expect(j.tenant_id).toContain("00000000");
  });

  it("accepts ISO8601 response timestamps", () => {
    const j = edgeAgentRegisterResponseSchema.parse({
      edge_agent_id: "22222222-2222-4222-8222-222222222222",
      registered_at: "2026-04-28T12:00:00+00:00",
    });
    expect(j.edge_agent_id).toBeDefined();
  });
});
