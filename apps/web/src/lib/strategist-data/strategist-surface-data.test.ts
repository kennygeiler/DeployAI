import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  buildPhaseTrackingRows,
  EVENING_CANDIDATES,
  MORNING_DIGEST_TOP,
  PHASE_TRACKING_MOCK_TODAY,
  PHASE_TRACKING_ROWS,
} from "@/lib/epic8/mock-digest";

import type { AuthActor } from "@deployai/authz";

import {
  eveningSynthesisBannerMessage,
  loadEveningSynthesis,
  loadEveningSynthesisResult,
  loadMorningDigestTopItems,
  loadMorningDigestTopItemsResult,
  loadMorningDigestTopItemsResultForActor,
  loadPhaseTrackingRows,
  loadPhaseTrackingRowsResult,
  morningDigestBannerMessage,
  parseDigestTopItemsPayload,
  parseEveningSynthesisPayload,
  parsePhaseTrackingRowsPayload,
  phaseTrackingBannerMessage,
  resolveStrategistEvidenceForActor,
} from "./strategist-surface-data";

describe("parseDigestTopItemsPayload", () => {
  it("returns null for non-array or empty array", () => {
    expect(parseDigestTopItemsPayload(null)).toBeNull();
    expect(parseDigestTopItemsPayload([])).toBeNull();
  });

  it("returns null when any row fails validation", () => {
    const bad = structuredClone(MORNING_DIGEST_TOP);
    (bad[0] as { state?: string }).state = "not-a-state";
    expect(parseDigestTopItemsPayload(bad)).toBeNull();
  });

  it("accepts a valid digest array", () => {
    const rows = structuredClone(MORNING_DIGEST_TOP);
    const parsed = parseDigestTopItemsPayload(rows);
    expect(parsed).not.toBeNull();
    expect(parsed!.length).toBe(3);
    expect(parsed![0]!.id).toBe(MORNING_DIGEST_TOP[0]!.id);
  });
});

describe("morningDigestBannerMessage", () => {
  it("returns null unless degraded", () => {
    expect(morningDigestBannerMessage({ items: MORNING_DIGEST_TOP, source: "mock" })).toBeNull();
    expect(
      morningDigestBannerMessage({
        items: MORNING_DIGEST_TOP,
        source: "live",
      }),
    ).toBeNull();
  });

  it("maps degraded reasons to user-safe copy", () => {
    expect(
      morningDigestBannerMessage({
        items: MORNING_DIGEST_TOP,
        source: "degraded",
        degradedReason: "fetch_error",
      }),
    ).toContain("Could not reach");
    expect(
      morningDigestBannerMessage({
        items: MORNING_DIGEST_TOP,
        source: "degraded",
        degradedReason: "http_error",
        httpStatus: 503,
      }),
    ).toContain("503");
    expect(
      morningDigestBannerMessage({
        items: MORNING_DIGEST_TOP,
        source: "degraded",
        degradedReason: "invalid_payload",
      }),
    ).toContain("validate");
    expect(
      morningDigestBannerMessage({
        items: MORNING_DIGEST_TOP,
        source: "degraded",
        degradedReason: "empty_array",
      }),
    ).toContain("no rows");
    expect(
      morningDigestBannerMessage({
        items: MORNING_DIGEST_TOP,
        source: "degraded",
        degradedReason: "tenant_required",
      }),
    ).toContain("tenant id");
    expect(
      morningDigestBannerMessage({
        items: MORNING_DIGEST_TOP,
        source: "degraded",
        degradedReason: "cp_unconfigured",
      }),
    ).toContain("internal API key");
    expect(
      morningDigestBannerMessage({
        items: [],
        source: "degraded",
        degradedReason: "cp_not_configured",
      }),
    ).toContain("pilot digest");
  });
});

describe("loadMorningDigestTopItemsResultForActor", () => {
  const originalFetch = globalThis.fetch;
  const originalDigestSource = process.env.DEPLOYAI_DIGEST_SOURCE;
  const originalCp = process.env.DEPLOYAI_CONTROL_PLANE_URL;
  const originalKey = process.env.DEPLOYAI_INTERNAL_API_KEY;

  const originalPilotTenant = process.env.DEPLOYAI_PILOT_TENANT_ID;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    if (originalDigestSource === undefined) {
      delete process.env.DEPLOYAI_DIGEST_SOURCE;
    } else {
      process.env.DEPLOYAI_DIGEST_SOURCE = originalDigestSource;
    }
    if (originalCp === undefined) {
      delete process.env.DEPLOYAI_CONTROL_PLANE_URL;
    } else {
      process.env.DEPLOYAI_CONTROL_PLANE_URL = originalCp;
    }
    if (originalKey === undefined) {
      delete process.env.DEPLOYAI_INTERNAL_API_KEY;
    } else {
      process.env.DEPLOYAI_INTERNAL_API_KEY = originalKey;
    }
    if (originalPilotTenant === undefined) {
      delete process.env.DEPLOYAI_PILOT_TENANT_ID;
    } else {
      process.env.DEPLOYAI_PILOT_TENANT_ID = originalPilotTenant;
    }
  });

  it("loads from control plane when DEPLOYAI_DIGEST_SOURCE=cp", async () => {
    process.env.DEPLOYAI_DIGEST_SOURCE = "cp";
    process.env.DEPLOYAI_CONTROL_PLANE_URL = "http://cp.test";
    process.env.DEPLOYAI_INTERNAL_API_KEY = "secret";
    const one = structuredClone(MORNING_DIGEST_TOP)[0]!;
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [one] }),
    });
    globalThis.fetch = fetchMock as typeof fetch;
    const actor: AuthActor = {
      role: "deployment_strategist",
      tenantId: "11111111-1111-4111-8111-111111111111",
    };
    const r = await loadMorningDigestTopItemsResultForActor(actor);
    expect(r.source).toBe("live");
    expect(r.items).toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://cp.test/internal/v1/strategist/pilot-surfaces/morning-digest-top?tenant_id=11111111-1111-4111-8111-111111111111",
      expect.objectContaining({
        headers: { "X-DeployAI-Internal-Key": "secret" },
      }),
    );
  });

  it("loads from control plane when DEPLOYAI_PILOT_TENANT_ID matches actor tenant", async () => {
    delete process.env.DEPLOYAI_DIGEST_SOURCE;
    process.env.DEPLOYAI_PILOT_TENANT_ID = "22222222-2222-4222-8222-222222222222";
    process.env.DEPLOYAI_CONTROL_PLANE_URL = "http://cp.test";
    process.env.DEPLOYAI_INTERNAL_API_KEY = "secret";
    const one = structuredClone(MORNING_DIGEST_TOP)[0]!;
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [one] }),
    });
    globalThis.fetch = fetchMock as typeof fetch;
    const actor: AuthActor = {
      role: "deployment_strategist",
      tenantId: "22222222-2222-4222-8222-222222222222",
    };
    const r = await loadMorningDigestTopItemsResultForActor(actor);
    expect(r.source).toBe("live");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://cp.test/internal/v1/strategist/pilot-surfaces/morning-digest-top?tenant_id=22222222-2222-4222-8222-222222222222",
      expect.objectContaining({
        headers: { "X-DeployAI-Internal-Key": "secret" },
      }),
    );
  });
});

describe("loadMorningDigestTopItemsResult", () => {
  const originalFetch = globalThis.fetch;
  const originalUrl = process.env.STRATEGIST_DIGEST_SOURCE_URL;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    if (originalUrl === undefined) {
      delete process.env.STRATEGIST_DIGEST_SOURCE_URL;
    } else {
      process.env.STRATEGIST_DIGEST_SOURCE_URL = originalUrl;
    }
  });

  it("returns mock when digest URL is unset", async () => {
    delete process.env.STRATEGIST_DIGEST_SOURCE_URL;
    const r = await loadMorningDigestTopItemsResult();
    expect(r.source).toBe("mock");
    expect(r.items).toEqual(MORNING_DIGEST_TOP);
    expect(r.degradedReason).toBeUndefined();
  });

  it("returns live when remote returns valid JSON array", async () => {
    process.env.STRATEGIST_DIGEST_SOURCE_URL = "https://digest.example/items.json";
    const body = structuredClone(MORNING_DIGEST_TOP);
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ) as unknown as typeof fetch;

    const r = await loadMorningDigestTopItemsResult();
    expect(r.source).toBe("live");
    expect(r.items.length).toBe(3);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "https://digest.example/items.json",
      expect.objectContaining({ cache: "no-store" }),
    );
  });

  it("returns degraded on HTTP error with mock items", async () => {
    process.env.STRATEGIST_DIGEST_SOURCE_URL = "https://digest.example/items.json";
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(new Response("", { status: 502 })) as unknown as typeof fetch;

    const r = await loadMorningDigestTopItemsResult();
    expect(r.source).toBe("degraded");
    expect(r.degradedReason).toBe("http_error");
    expect(r.httpStatus).toBe(502);
    expect(r.items).toEqual(MORNING_DIGEST_TOP);
  });

  it("returns degraded on invalid JSON body", async () => {
    process.env.STRATEGIST_DIGEST_SOURCE_URL = "https://digest.example/items.json";
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(new Response("not json", { status: 200 })) as unknown as typeof fetch;

    const r = await loadMorningDigestTopItemsResult();
    expect(r.source).toBe("degraded");
    expect(r.degradedReason).toBe("invalid_payload");
    expect(r.items).toEqual(MORNING_DIGEST_TOP);
  });

  it("returns degraded on empty array", async () => {
    process.env.STRATEGIST_DIGEST_SOURCE_URL = "https://digest.example/items.json";
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify([]), { status: 200 }),
      ) as unknown as typeof fetch;

    const r = await loadMorningDigestTopItemsResult();
    expect(r.source).toBe("degraded");
    expect(r.degradedReason).toBe("empty_array");
  });

  it("returns degraded on fetch failure", async () => {
    process.env.STRATEGIST_DIGEST_SOURCE_URL = "https://digest.example/items.json";
    globalThis.fetch = vi.fn().mockRejectedValue(new Error("network")) as unknown as typeof fetch;

    const r = await loadMorningDigestTopItemsResult();
    expect(r.source).toBe("degraded");
    expect(r.degradedReason).toBe("fetch_error");
  });

  it("loadMorningDigestTopItems returns items only", async () => {
    delete process.env.STRATEGIST_DIGEST_SOURCE_URL;
    const items = await loadMorningDigestTopItems();
    expect(items).toEqual(MORNING_DIGEST_TOP);
  });
});

describe("parsePhaseTrackingRowsPayload", () => {
  it("returns null for non-array or empty array", () => {
    expect(parsePhaseTrackingRowsPayload(null)).toBeNull();
    expect(parsePhaseTrackingRowsPayload([])).toBeNull();
  });

  it("returns null when any row fails validation", () => {
    const bad = structuredClone(PHASE_TRACKING_ROWS);
    (bad[0] as { status?: string }).status = "done";
    expect(parsePhaseTrackingRowsPayload(bad)).toBeNull();
  });

  it("accepts a valid action-queue array", () => {
    const rows = structuredClone(PHASE_TRACKING_ROWS);
    const parsed = parsePhaseTrackingRowsPayload(rows);
    expect(parsed).not.toBeNull();
    expect(parsed!.length).toBe(4);
    expect(parsed![0]!.id).toBe(PHASE_TRACKING_ROWS[0]!.id);
  });
});

describe("phaseTrackingBannerMessage", () => {
  const rows = PHASE_TRACKING_ROWS;

  it("returns null unless degraded", () => {
    expect(phaseTrackingBannerMessage({ items: rows, source: "mock" })).toBeNull();
    expect(phaseTrackingBannerMessage({ items: rows, source: "live" })).toBeNull();
  });

  it("maps degraded reasons to user-safe copy", () => {
    expect(
      phaseTrackingBannerMessage({
        items: rows,
        source: "degraded",
        degradedReason: "fetch_error",
      }),
    ).toContain("Could not reach");
    expect(
      phaseTrackingBannerMessage({
        items: rows,
        source: "degraded",
        degradedReason: "http_error",
        httpStatus: 503,
      }),
    ).toContain("503");
    expect(
      phaseTrackingBannerMessage({
        items: rows,
        source: "degraded",
        degradedReason: "invalid_payload",
      }),
    ).toContain("validate");
    expect(
      phaseTrackingBannerMessage({
        items: rows,
        source: "degraded",
        degradedReason: "empty_array",
      }),
    ).toContain("no rows");
    expect(
      phaseTrackingBannerMessage({
        items: [],
        source: "degraded",
        degradedReason: "cp_not_configured",
      }),
    ).toContain("phase-tracking");
  });
});

describe("loadPhaseTrackingRowsResult", () => {
  const originalFetch = globalThis.fetch;
  const originalUrl = process.env.STRATEGIST_PHASE_TRACKING_SOURCE_URL;
  const today = PHASE_TRACKING_MOCK_TODAY;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    if (originalUrl === undefined) {
      delete process.env.STRATEGIST_PHASE_TRACKING_SOURCE_URL;
    } else {
      process.env.STRATEGIST_PHASE_TRACKING_SOURCE_URL = originalUrl;
    }
  });

  it("returns mock when phase-tracking URL is unset", async () => {
    delete process.env.STRATEGIST_PHASE_TRACKING_SOURCE_URL;
    const r = await loadPhaseTrackingRowsResult(today);
    expect(r.source).toBe("mock");
    expect(r.items).toEqual(buildPhaseTrackingRows(today));
    expect(r.degradedReason).toBeUndefined();
  });

  it("returns live when remote returns valid JSON array", async () => {
    process.env.STRATEGIST_PHASE_TRACKING_SOURCE_URL = "https://phase.example/rows.json";
    const body = structuredClone(PHASE_TRACKING_ROWS);
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ) as unknown as typeof fetch;

    const r = await loadPhaseTrackingRowsResult(today);
    expect(r.source).toBe("live");
    expect(r.items.length).toBe(4);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "https://phase.example/rows.json",
      expect.objectContaining({ cache: "no-store" }),
    );
  });

  it("returns degraded on HTTP error with fallback rows", async () => {
    process.env.STRATEGIST_PHASE_TRACKING_SOURCE_URL = "https://phase.example/rows.json";
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(new Response("", { status: 502 })) as unknown as typeof fetch;

    const r = await loadPhaseTrackingRowsResult(today);
    expect(r.source).toBe("degraded");
    expect(r.degradedReason).toBe("http_error");
    expect(r.items).toEqual(buildPhaseTrackingRows(today));
  });

  it("loadPhaseTrackingRows returns items only", async () => {
    delete process.env.STRATEGIST_PHASE_TRACKING_SOURCE_URL;
    const items = await loadPhaseTrackingRows(today);
    expect(items).toEqual(buildPhaseTrackingRows(today));
  });
});

describe("parseEveningSynthesisPayload", () => {
  it("returns null when root is not an object", () => {
    expect(parseEveningSynthesisPayload(null)).toBeNull();
    expect(parseEveningSynthesisPayload([])).toBeNull();
  });

  it("returns null when candidates missing or invalid", () => {
    expect(parseEveningSynthesisPayload({ patterns: EVENING_CANDIDATES })).toBeNull();
    expect(parseEveningSynthesisPayload({ candidates: [] })).toBeNull();
  });

  it("rejects invalid pattern rows", () => {
    const bad = {
      candidates: structuredClone(MORNING_DIGEST_TOP),
      patterns: [{ id: "x", title: "t" }],
    };
    expect(parseEveningSynthesisPayload(bad)).toBeNull();
  });

  it("accepts candidates with optional patterns", () => {
    const p = parseEveningSynthesisPayload({
      candidates: structuredClone(MORNING_DIGEST_TOP),
    });
    expect(p).not.toBeNull();
    expect(p!.candidates.length).toBe(3);
    expect(p!.patterns).toEqual([]);
  });

  it("accepts candidates and patterns together", () => {
    const p = parseEveningSynthesisPayload({
      candidates: structuredClone(MORNING_DIGEST_TOP),
      patterns: structuredClone(EVENING_CANDIDATES),
    });
    expect(p!.patterns).toHaveLength(2);
  });
});

describe("eveningSynthesisBannerMessage", () => {
  const fb = {
    candidates: MORNING_DIGEST_TOP.slice(0, 2),
    patterns: EVENING_CANDIDATES,
  };

  it("returns null unless degraded", () => {
    expect(eveningSynthesisBannerMessage({ ...fb, source: "mock" })).toBeNull();
    expect(eveningSynthesisBannerMessage({ ...fb, source: "live" })).toBeNull();
  });

  it("includes HTTP status when degraded", () => {
    expect(
      eveningSynthesisBannerMessage({
        ...fb,
        source: "degraded",
        degradedReason: "http_error",
        httpStatus: 418,
      }),
    ).toContain("418");
  });

  it("maps pilot CP unconfigured reasons", () => {
    expect(
      eveningSynthesisBannerMessage({
        ...fb,
        source: "degraded",
        degradedReason: "cp_not_configured",
      }),
    ).toContain("evening synthesis");
  });
});

describe("loadEveningSynthesisResult", () => {
  const originalFetch = globalThis.fetch;
  const originalUrl = process.env.STRATEGIST_EVENING_SYNTHESIS_SOURCE_URL;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    if (originalUrl === undefined) {
      delete process.env.STRATEGIST_EVENING_SYNTHESIS_SOURCE_URL;
    } else {
      process.env.STRATEGIST_EVENING_SYNTHESIS_SOURCE_URL = originalUrl;
    }
  });

  it("returns mock when URL unset", async () => {
    delete process.env.STRATEGIST_EVENING_SYNTHESIS_SOURCE_URL;
    const r = await loadEveningSynthesisResult();
    expect(r.source).toBe("mock");
    expect(r.candidates).toEqual(MORNING_DIGEST_TOP.slice(0, 2));
    expect(r.patterns).toEqual(EVENING_CANDIDATES);
  });

  it("returns live on valid remote object", async () => {
    process.env.STRATEGIST_EVENING_SYNTHESIS_SOURCE_URL = "https://evening.example/synthesis.json";
    const body = {
      candidates: structuredClone(MORNING_DIGEST_TOP),
      patterns: structuredClone(EVENING_CANDIDATES),
    };
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ) as unknown as typeof fetch;

    const r = await loadEveningSynthesisResult();
    expect(r.source).toBe("live");
    expect(r.candidates.length).toBe(3);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "https://evening.example/synthesis.json",
      expect.objectContaining({ cache: "no-store" }),
    );
  });

  it("loadEveningSynthesis returns candidates and patterns only", async () => {
    delete process.env.STRATEGIST_EVENING_SYNTHESIS_SOURCE_URL;
    const r = await loadEveningSynthesis();
    expect(r.candidates).toEqual(MORNING_DIGEST_TOP.slice(0, 2));
    expect(r.patterns).toEqual(EVENING_CANDIDATES);
  });
});

describe("resolveStrategistEvidenceForActor", () => {
  const originalFetch = globalThis.fetch;
  const originalEvidence = process.env.DEPLOYAI_EVIDENCE_SOURCE;
  const originalPilotTenant = process.env.DEPLOYAI_PILOT_TENANT_ID;
  const originalCp = process.env.DEPLOYAI_CONTROL_PLANE_URL;
  const originalKey = process.env.DEPLOYAI_INTERNAL_API_KEY;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    if (originalEvidence === undefined) {
      delete process.env.DEPLOYAI_EVIDENCE_SOURCE;
    } else {
      process.env.DEPLOYAI_EVIDENCE_SOURCE = originalEvidence;
    }
    if (originalPilotTenant === undefined) {
      delete process.env.DEPLOYAI_PILOT_TENANT_ID;
    } else {
      process.env.DEPLOYAI_PILOT_TENANT_ID = originalPilotTenant;
    }
    if (originalCp === undefined) {
      delete process.env.DEPLOYAI_CONTROL_PLANE_URL;
    } else {
      process.env.DEPLOYAI_CONTROL_PLANE_URL = originalCp;
    }
    if (originalKey === undefined) {
      delete process.env.DEPLOYAI_INTERNAL_API_KEY;
    } else {
      process.env.DEPLOYAI_INTERNAL_API_KEY = originalKey;
    }
  });

  it("returns ok from mock fixtures when CP evidence mode is off", async () => {
    delete process.env.DEPLOYAI_EVIDENCE_SOURCE;
    delete process.env.DEPLOYAI_PILOT_TENANT_ID;
    const actor: AuthActor = {
      role: "deployment_strategist",
      tenantId: undefined,
    };
    const id = MORNING_DIGEST_TOP[0]!.id;
    const r = await resolveStrategistEvidenceForActor(actor, id);
    expect(r.status).toBe("ok");
    if (r.status === "ok") {
      expect(r.item.id).toBe(id);
    }
  });

  it("returns not_found when CP responds 404", async () => {
    process.env.DEPLOYAI_EVIDENCE_SOURCE = "cp";
    process.env.DEPLOYAI_CONTROL_PLANE_URL = "http://cp.test";
    process.env.DEPLOYAI_INTERNAL_API_KEY = "secret";
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false, status: 404 }) as unknown as typeof fetch;
    const actor: AuthActor = {
      role: "deployment_strategist",
      tenantId: "11111111-1111-4111-8111-111111111111",
    };
    const r = await resolveStrategistEvidenceForActor(actor, "any-node-id");
    expect(r.status).toBe("not_found");
  });

  it("returns not_found when payload id does not match requested node id", async () => {
    process.env.DEPLOYAI_EVIDENCE_SOURCE = "cp";
    process.env.DEPLOYAI_CONTROL_PLANE_URL = "http://cp.test";
    process.env.DEPLOYAI_INTERNAL_API_KEY = "secret";
    const payload = structuredClone(MORNING_DIGEST_TOP)[0]!;
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => payload,
    }) as unknown as typeof fetch;
    const actor: AuthActor = {
      role: "deployment_strategist",
      tenantId: "11111111-1111-4111-8111-111111111111",
    };
    const r = await resolveStrategistEvidenceForActor(actor, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
    expect(r.status).toBe("not_found");
  });

  it("returns ok when CP returns a body whose id matches the requested node id", async () => {
    process.env.DEPLOYAI_EVIDENCE_SOURCE = "cp";
    process.env.DEPLOYAI_CONTROL_PLANE_URL = "http://cp.test";
    process.env.DEPLOYAI_INTERNAL_API_KEY = "secret";
    const payload = structuredClone(MORNING_DIGEST_TOP)[0]!;
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => payload,
    }) as unknown as typeof fetch;
    const actor: AuthActor = {
      role: "deployment_strategist",
      tenantId: "11111111-1111-4111-8111-111111111111",
    };
    const r = await resolveStrategistEvidenceForActor(actor, payload.id);
    expect(r.status).toBe("ok");
    if (r.status === "ok") {
      expect(r.item.id).toBe(payload.id);
    }
  });

  it("returns cp_unconfigured when CP evidence mode is on but control plane URL is missing", async () => {
    process.env.DEPLOYAI_EVIDENCE_SOURCE = "cp";
    delete process.env.DEPLOYAI_CONTROL_PLANE_URL;
    process.env.DEPLOYAI_INTERNAL_API_KEY = "secret";
    const actor: AuthActor = {
      role: "deployment_strategist",
      tenantId: "11111111-1111-4111-8111-111111111111",
    };
    const r = await resolveStrategistEvidenceForActor(actor, MORNING_DIGEST_TOP[0]!.id);
    expect(r.status).toBe("cp_unconfigured");
  });
});
