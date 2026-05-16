import { afterEach, describe, expect, it, vi } from "vitest";

import {
  shouldStripInboundStrategistHeadersBeforeJwt,
  stripInboundStrategistHeadersBeforeJwt,
} from "./strategist-header-strip-before-jwt";

describe("stripInboundStrategistHeadersBeforeJwt", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.stubEnv("DEPLOYAI_WEB_CLEAR_STRATEGIST_HEADERS_BEFORE_JWT", undefined);
    vi.stubEnv("DEPLOYAI_WEB_TRUST_JWT", undefined);
    vi.stubEnv("DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM", undefined);
  });

  it("is inactive when CLEAR flag is unset", () => {
    vi.stubEnv("DEPLOYAI_WEB_TRUST_JWT", "1");
    vi.stubEnv("DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM", "-----BEGIN PUBLIC KEY-----\nfake\n-----END PUBLIC KEY-----");
    expect(shouldStripInboundStrategistHeadersBeforeJwt()).toBe(false);

    const h = new Headers({ "x-deployai-role": "deployment_strategist", "x-deployai-tenant": "t1" });
    stripInboundStrategistHeadersBeforeJwt(h);
    expect(h.get("x-deployai-role")).toBe("deployment_strategist");
  });

  it("is inactive when PEM is blank", () => {
    vi.stubEnv("DEPLOYAI_WEB_CLEAR_STRATEGIST_HEADERS_BEFORE_JWT", "1");
    vi.stubEnv("DEPLOYAI_WEB_TRUST_JWT", "1");
    vi.stubEnv("DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM", "   ");
    expect(shouldStripInboundStrategistHeadersBeforeJwt()).toBe(false);
  });

  it("when active, clears role and tenant headers", () => {
    vi.stubEnv("DEPLOYAI_WEB_CLEAR_STRATEGIST_HEADERS_BEFORE_JWT", "1");
    vi.stubEnv("DEPLOYAI_WEB_TRUST_JWT", "1");
    vi.stubEnv("DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM", "-----BEGIN PUBLIC KEY-----\nfake\n-----END PUBLIC KEY-----");

    expect(shouldStripInboundStrategistHeadersBeforeJwt()).toBe(true);

    const h = new Headers({
      "x-deployai-role": "deployment_strategist",
      "x-deployai-tenant": "00000000-0000-4000-8000-000000000001",
    });
    stripInboundStrategistHeadersBeforeJwt(h);
    expect(h.get("x-deployai-role")).toBeNull();
    expect(h.get("x-deployai-tenant")).toBeNull();
  });
});
