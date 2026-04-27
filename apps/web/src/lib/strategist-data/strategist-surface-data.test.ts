import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  buildPhaseTrackingRows,
  MORNING_DIGEST_TOP,
  PHASE_TRACKING_MOCK_TODAY,
  PHASE_TRACKING_ROWS,
} from "@/lib/epic8/mock-digest";

import {
  loadMorningDigestTopItems,
  loadMorningDigestTopItemsResult,
  loadPhaseTrackingRows,
  loadPhaseTrackingRowsResult,
  morningDigestBannerMessage,
  parseDigestTopItemsPayload,
  parsePhaseTrackingRowsPayload,
  phaseTrackingBannerMessage,
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
