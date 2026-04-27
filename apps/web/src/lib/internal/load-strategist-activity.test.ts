import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { loadStrategistActivityForActor } from "./load-strategist-activity";

function meetingOffResponse() {
  return new Response(
    JSON.stringify({
      in_meeting: false,
      meeting_id: null,
      meeting_title: null,
      oracle_in_meeting_alert_at: null,
    }),
    { status: 200, headers: { "content-type": "application/json" } },
  );
}

describe("loadStrategistActivityForActor", () => {
  const original = globalThis.fetch;
  const originalBase = process.env.DEPLOYAI_CONTROL_PLANE_URL;
  const originalKey = process.env.DEPLOYAI_INTERNAL_API_KEY;
  const originalOracle = process.env.DEPLOYAI_ORACLE_HEALTH_URL;

  beforeEach(() => {
    process.env.DEPLOYAI_CONTROL_PLANE_URL = "https://cp.test";
    process.env.DEPLOYAI_INTERNAL_API_KEY = "k";
    delete process.env.DEPLOYAI_ORACLE_HEALTH_URL;
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
    if (originalOracle === undefined) {
      delete process.env.DEPLOYAI_ORACLE_HEALTH_URL;
    } else {
      process.env.DEPLOYAI_ORACLE_HEALTH_URL = originalOracle;
    }
    vi.restoreAllMocks();
  });

  it("ingestion in progress for tenant with a running run", async () => {
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo) => {
      const u = typeof input === "string" ? input : String(input);
      if (u.includes("/healthz")) {
        return Promise.resolve(new Response(JSON.stringify({ status: "ok" }), { status: 200 }));
      }
      if (u.includes("meeting-presence")) {
        return Promise.resolve(meetingOffResponse());
      }
      if (u.includes("ingestion-runs")) {
        return Promise.resolve(
          new Response(
            JSON.stringify([
              { tenant_id: "t1", status: "succeeded" },
              { tenant_id: "t1", status: "running" },
            ]),
            { status: 200, headers: { "content-type": "application/json" } },
          ),
        );
      }
      return Promise.reject(new Error(`unexpected fetch ${u}`));
    }) as unknown as typeof fetch;
    const r = await loadStrategistActivityForActor({
      role: "deployment_strategist",
      tenantId: "t1",
    });
    expect(r).toMatchObject({
      agentDegraded: false,
      ingestionInProgress: true,
      strategistLocalDate: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      controlPlane: "ok",
      agentServiceHealth: "unconfigured",
      inMeeting: false,
    });
  });

  it("ingestion off when no running for tenant", async () => {
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo) => {
      const u = typeof input === "string" ? input : String(input);
      if (u.includes("/healthz")) {
        return Promise.resolve(new Response(JSON.stringify({ status: "ok" }), { status: 200 }));
      }
      if (u.includes("meeting-presence")) {
        return Promise.resolve(meetingOffResponse());
      }
      if (u.includes("ingestion-runs")) {
        return Promise.resolve(
          new Response(JSON.stringify([{ tenant_id: "t1", status: "succeeded" }]), {
            status: 200,
          }),
        );
      }
      return Promise.reject(new Error(`unexpected fetch ${u}`));
    }) as unknown as typeof fetch;
    const r = await loadStrategistActivityForActor({
      role: "deployment_strategist",
      tenantId: "t1",
    });
    expect(r.ingestionInProgress).toBe(false);
    expect(r.controlPlane).toBe("ok");
  });

  it("FR47: no tenant id — do not use other tenants' running runs", async () => {
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo) => {
      const u = typeof input === "string" ? input : String(input);
      if (u.includes("/healthz")) {
        return Promise.resolve(new Response(JSON.stringify({ status: "ok" }), { status: 200 }));
      }
      if (u.includes("ingestion-runs")) {
        return Promise.resolve(
          new Response(JSON.stringify([{ tenant_id: "t9", status: "running" }]), { status: 200 }),
        );
      }
      return Promise.reject(new Error(`unexpected fetch ${u}`));
    }) as unknown as typeof fetch;
    const r = await loadStrategistActivityForActor({
      role: "deployment_strategist",
    });
    expect(r.ingestionInProgress).toBe(false);
  });

  it("agentDegraded when healthz is not ok", async () => {
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo) => {
      const u = typeof input === "string" ? input : String(input);
      if (u.includes("/healthz")) {
        return Promise.resolve(new Response("{}", { status: 503 }));
      }
      return Promise.reject(new Error(`unexpected fetch ${u}`));
    }) as unknown as typeof fetch;
    const r = await loadStrategistActivityForActor({
      role: "deployment_strategist",
      tenantId: "t1",
    });
    expect(r.controlPlane).toBe("error");
    expect(r.agentDegraded).toBe(true);
  });

  it("agentDegraded on fetch error (after healthz)", async () => {
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo) => {
      const u = typeof input === "string" ? input : String(input);
      if (u.includes("/healthz")) {
        return Promise.resolve(new Response(JSON.stringify({ status: "ok" }), { status: 200 }));
      }
      if (u.includes("meeting-presence")) {
        return Promise.resolve(meetingOffResponse());
      }
      if (u.includes("ingestion-runs")) {
        return Promise.reject(new TypeError("network"));
      }
      return Promise.reject(new Error(`unexpected fetch ${u}`));
    }) as unknown as typeof fetch;
    const r = await loadStrategistActivityForActor({
      role: "deployment_strategist",
      tenantId: "t1",
    });
    expect(r).toMatchObject({
      agentDegraded: true,
      ingestionInProgress: false,
      strategistLocalDate: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      controlPlane: "error",
      agentServiceHealth: "unconfigured",
      inMeeting: false,
    });
  });
});
