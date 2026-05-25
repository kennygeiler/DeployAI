import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

describe("GET /api/auth/callback/oidc (stub)", () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("returns 503 oidc-not-configured when issuer env is unset", async () => {
    vi.stubEnv("DEPLOYAI_OIDC_ISSUER", "");
    const res = GET();
    expect(res.status).toBe(503);
    expect(await res.text()).toBe("oidc-not-configured");
  });

  it("returns 501 stub-pending when issuer env is set", async () => {
    vi.stubEnv("DEPLOYAI_OIDC_ISSUER", "http://keycloak:8080/realms/deployai");
    const res = GET();
    expect(res.status).toBe(501);
    expect(await res.text()).toBe("oidc-callback-stub-pending-jwt-verify");
  });
});
