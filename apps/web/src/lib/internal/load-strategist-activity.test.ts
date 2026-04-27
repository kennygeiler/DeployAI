import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { loadStrategistActivityForActor } from "./load-strategist-activity";

describe("loadStrategistActivityForActor", () => {
  const original = globalThis.fetch;
  const originalBase = process.env.DEPLOYAI_CONTROL_PLANE_URL;
  const originalKey = process.env.DEPLOYAI_INTERNAL_API_KEY;

  beforeEach(() => {
    process.env.DEPLOYAI_CONTROL_PLANE_URL = "https://cp.test";
    process.env.DEPLOYAI_INTERNAL_API_KEY = "k";
  });

  afterEach(() => {
    globalThis.fetch = original;
    if (originalBase === undefined) {
      delete process.env.DEPLOYAI_CONTROL_PLANE_URL;
    } else {
      process.env.DEPLOYAI_CONTROL_PLANE_URL = originalBase;
    }
    if (originalKey === undefined) {
      delete process.env.DEPLOYAI_INTERNAL_API_KEY;
    } else {
      process.env.DEPLOYAI_INTERNAL_API_KEY = originalKey;
    }
    vi.restoreAllMocks();
  });

  it("ingestion in progress for tenant with a running run", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify([
          { tenant_id: "t1", status: "succeeded" },
          { tenant_id: "t1", status: "running" },
        ]),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    ) as unknown as typeof fetch;
    const r = await loadStrategistActivityForActor({
      role: "deployment_strategist",
      tenantId: "t1",
    });
    expect(r).toEqual({
      agentDegraded: false,
      ingestionInProgress: true,
      strategistLocalDate: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      controlPlane: "ok",
    });
  });

  it("ingestion off when no running for tenant", async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify([{ tenant_id: "t1", status: "succeeded" }]), { status: 200 }),
      ) as unknown as typeof fetch;
    const r = await loadStrategistActivityForActor({
      role: "deployment_strategist",
      tenantId: "t1",
    });
    expect(r.ingestionInProgress).toBe(false);
    expect(r.controlPlane).toBe("ok");
  });

  it("agentDegraded on fetch error", async () => {
    globalThis.fetch = vi
      .fn()
      .mockRejectedValue(new TypeError("network")) as unknown as typeof fetch;
    const r = await loadStrategistActivityForActor({
      role: "deployment_strategist",
      tenantId: "t1",
    });
    expect(r).toEqual({
      agentDegraded: true,
      ingestionInProgress: false,
      strategistLocalDate: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      controlPlane: "error",
    });
  });
});
