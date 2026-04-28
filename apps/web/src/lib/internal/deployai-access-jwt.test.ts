/** @vitest-environment node */
import * as jose from "jose";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  applyDeployaiAccessJwtToHeaders,
  extractBearerToken,
  jwtAudienceFromEnv,
  jwtIssuerFromEnv,
  normalizePemFromEnv,
  splitPublicPemBlocks,
  verifyDeployaiAccessJwt,
  v1RoleFromJwtRoles,
} from "./deployai-access-jwt";

describe("deployai-access-jwt", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("normalizePemFromEnv expands escaped newlines", () => {
    const oneLine = "-----BEGIN\\nLINE\\n-----END";
    expect(normalizePemFromEnv(oneLine)).toBe("-----BEGIN\nLINE\n-----END");
  });

  it("splitPublicPemBlocks splits concatenated SPKI blocks", () => {
    const a =
      "-----BEGIN PUBLIC KEY-----\nAA\n-----END PUBLIC KEY-----\n-----BEGIN PUBLIC KEY-----\nBB\n-----END PUBLIC KEY-----";
    const parts = splitPublicPemBlocks(a);
    expect(parts).toHaveLength(2);
    expect(parts[0]).toContain("AA");
    expect(parts[1]).toContain("BB");
  });

  it("v1RoleFromJwtRoles picks highest-priority known role", () => {
    expect(v1RoleFromJwtRoles(["deployment_strategist", "customer_admin"])).toBe("customer_admin");
    expect(v1RoleFromJwtRoles(["external_auditor", "deployment_strategist"])).toBe(
      "deployment_strategist",
    );
    expect(v1RoleFromJwtRoles(["unknown"])).toBeNull();
  });

  it("extractBearerToken parses Authorization header", () => {
    expect(extractBearerToken("Bearer abc.def")).toBe("abc.def");
    expect(extractBearerToken("Basic x")).toBeNull();
    expect(extractBearerToken(null)).toBeNull();
  });

  it("jwtIssuerFromEnv / jwtAudienceFromEnv use CP defaults", () => {
    expect(jwtIssuerFromEnv()).toBe("deployai-control-plane");
    expect(jwtAudienceFromEnv()).toBe("deployai");
    vi.stubEnv("DEPLOYAI_JWT_ISSUER", "custom-iss");
    vi.stubEnv("DEPLOYAI_JWT_AUDIENCE", "custom-aud");
    expect(jwtIssuerFromEnv()).toBe("custom-iss");
    expect(jwtAudienceFromEnv()).toBe("custom-aud");
  });

  it("verifyDeployaiAccessJwt verifies RS256 access token from CP-shaped claims", async () => {
    const { publicKey, privateKey } = await jose.generateKeyPair("RS256");
    const pubPem = await jose.exportSPKI(publicKey);
    vi.stubEnv("DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM", pubPem);
    const now = Math.floor(Date.now() / 1000);
    const jwt = await new jose.SignJWT({
      sub: "user-1",
      tid: "11111111-1111-4111-8111-111111111111",
      roles: ["deployment_strategist"],
      token_use: "access",
    })
      .setProtectedHeader({ alg: "RS256" })
      .setIssuer("deployai-control-plane")
      .setAudience("deployai")
      .setIssuedAt(now)
      .setExpirationTime(now + 120)
      .sign(privateKey);

    const claims = await verifyDeployaiAccessJwt(jwt);
    expect(claims).toEqual({
      sub: "user-1",
      tid: "11111111-1111-4111-8111-111111111111",
      roles: ["deployment_strategist"],
    });
  });

  it("verifyDeployaiAccessJwt rejects wrong token_use when set", async () => {
    const { publicKey, privateKey } = await jose.generateKeyPair("RS256");
    vi.stubEnv("DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM", await jose.exportSPKI(publicKey));
    const now = Math.floor(Date.now() / 1000);
    const jwt = await new jose.SignJWT({
      sub: "u",
      tid: "11111111-1111-4111-8111-111111111111",
      roles: ["deployment_strategist"],
      token_use: "refresh",
    })
      .setProtectedHeader({ alg: "RS256" })
      .setIssuer("deployai-control-plane")
      .setAudience("deployai")
      .setIssuedAt(now)
      .setExpirationTime(now + 120)
      .sign(privateKey);

    await expect(verifyDeployaiAccessJwt(jwt)).resolves.toBeNull();
  });

  it("applyDeployaiAccessJwtToHeaders sets role and tenant when trust + PEM", async () => {
    const { publicKey, privateKey } = await jose.generateKeyPair("RS256");
    vi.stubEnv("DEPLOYAI_WEB_TRUST_JWT", "1");
    vi.stubEnv("DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM", await jose.exportSPKI(publicKey));
    const now = Math.floor(Date.now() / 1000);
    const tid = "22222222-2222-4222-8222-222222222222";
    const jwt = await new jose.SignJWT({
      sub: "user-2",
      tid,
      roles: ["deployment_strategist"],
      token_use: "access",
    })
      .setProtectedHeader({ alg: "RS256" })
      .setIssuer("deployai-control-plane")
      .setAudience("deployai")
      .setIssuedAt(now)
      .setExpirationTime(now + 120)
      .sign(privateKey);

    const h = new Headers();
    await expect(
      applyDeployaiAccessJwtToHeaders(`Bearer ${jwt}`, null, h),
    ).resolves.toBeUndefined();
    expect(h.get("x-deployai-role")).toBe("deployment_strategist");
    expect(h.get("x-deployai-tenant")).toBe(tid);
  });

  it("applyDeployaiAccessJwtToHeaders returns invalidToken when credentials present but verify fails", async () => {
    const { publicKey } = await jose.generateKeyPair("RS256");
    vi.stubEnv("DEPLOYAI_WEB_TRUST_JWT", "1");
    vi.stubEnv("DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM", await jose.exportSPKI(publicKey));
    const h = new Headers();
    await expect(applyDeployaiAccessJwtToHeaders("Bearer not-a-jwt", null, h)).resolves.toEqual({
      invalidToken: true,
    });
    expect(h.get("x-deployai-role")).toBeNull();
  });
});
