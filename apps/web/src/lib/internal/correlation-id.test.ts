import { describe, expect, it, vi } from "vitest";

import {
  ensureRequestCorrelationHeader,
  pickCorrelationIdFromIncoming,
  resolveStrategistOutboundCorrelationId,
} from "./correlation-id";

describe("pickCorrelationIdFromIncoming", () => {
  it("prefers x-deployai-correlation-id", () => {
    const h = new Headers();
    h.set("x-deployai-correlation-id", "abc");
    h.set("x-request-id", "req");
    expect(pickCorrelationIdFromIncoming(h)).toBe("abc");
  });

  it("falls back to x-request-id", () => {
    const h = new Headers();
    h.set("x-request-id", "req");
    expect(pickCorrelationIdFromIncoming(h)).toBe("req");
  });

  it("returns undefined when absent", () => {
    expect(pickCorrelationIdFromIncoming(new Headers())).toBeUndefined();
  });
});

describe("ensureRequestCorrelationHeader", () => {
  it("reuses correlation already copied onto the mutable header bag", () => {
    const incoming = new Headers();
    incoming.set("x-deployai-correlation-id", "abc");
    const target = new Headers(incoming);
    expect(ensureRequestCorrelationHeader(target, incoming)).toBe("abc");
    expect(target.get("x-deployai-correlation-id")).toBe("abc");
  });

  it("generates a UUID when missing", () => {
    vi.stubGlobal("crypto", { randomUUID: () => "00000000-0000-4000-8000-000000000001" });
    const target = new Headers();
    const incoming = new Headers();
    expect(ensureRequestCorrelationHeader(target, incoming)).toBe(
      "00000000-0000-4000-8000-000000000001",
    );
    vi.unstubAllGlobals();
  });
});

describe("resolveStrategistOutboundCorrelationId", () => {
  it("reuses inbound trimmed ids", () => {
    expect(resolveStrategistOutboundCorrelationId(" abc ")).toBe("abc");
  });

  it("generates when absent", () => {
    vi.stubGlobal("crypto", { randomUUID: () => "00000000-0000-4000-8000-000000000002" });
    expect(resolveStrategistOutboundCorrelationId(null)).toBe(
      "00000000-0000-4000-8000-000000000002",
    );
    vi.unstubAllGlobals();
  });
});
