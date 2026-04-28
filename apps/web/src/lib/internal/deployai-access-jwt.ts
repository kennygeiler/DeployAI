import * as jose from "jose";

import type { V1Role } from "@deployai/authz";

/** When multiple CP roles are present, pick the broadest V1 role for middleware (deterministic). */
const ROLE_PRIORITY: V1Role[] = [
  "platform_admin",
  "customer_admin",
  "deployment_strategist",
  "successor_strategist",
  "customer_records_officer",
  "external_auditor",
];

const spkiCache = new Map<string, Promise<CryptoKey>>();

export function normalizePemFromEnv(s: string): string {
  return s.replace(/\\n/g, "\n").trim();
}

/** Support one PEM or several concatenated blocks (key rotation). */
export function splitPublicPemBlocks(bundle: string): string[] {
  const n = normalizePemFromEnv(bundle);
  if (!n) {
    return [];
  }
  return n
    .split(/(?=-----BEGIN PUBLIC KEY-----)/)
    .map((b) => b.trim())
    .filter(Boolean);
}

function importSpki(pem: string): Promise<CryptoKey> {
  let p = spkiCache.get(pem);
  if (!p) {
    p = jose.importSPKI(pem, "RS256");
    spkiCache.set(pem, p);
  }
  return p;
}

export type DeployaiAccessClaims = {
  sub: string;
  tid: string;
  roles: string[];
};

export function v1RoleFromJwtRoles(roles: string[]): V1Role | null {
  const set = new Set(roles);
  for (const r of ROLE_PRIORITY) {
    if (set.has(r)) {
      return r;
    }
  }
  return null;
}

export function jwtIssuerFromEnv(): string {
  return process.env.DEPLOYAI_JWT_ISSUER ?? "deployai-control-plane";
}

export function jwtAudienceFromEnv(): string {
  return process.env.DEPLOYAI_JWT_AUDIENCE ?? "deployai";
}

export function accessTokenCookieNameFromEnv(): string {
  return process.env.DEPLOYAI_WEB_ACCESS_TOKEN_COOKIE ?? "deployai_access_token";
}

/**
 * Verify a control-plane access JWT (RS256, iss/aud, ~60s clock skew).
 * Returns null if env PEM is missing, signature fails, or claims are invalid.
 */
export async function verifyDeployaiAccessJwt(token: string): Promise<DeployaiAccessClaims | null> {
  const raw = process.env.DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM;
  if (!raw?.trim()) {
    return null;
  }
  const blocks = splitPublicPemBlocks(raw);
  if (!blocks.length) {
    return null;
  }
  const issuer = jwtIssuerFromEnv();
  const audience = jwtAudienceFromEnv();
  for (const pem of blocks) {
    try {
      const key = await importSpki(pem);
      const { payload } = await jose.jwtVerify(token, key, {
        issuer,
        audience,
        algorithms: ["RS256"],
        clockTolerance: 60,
      });
      if (payload.token_use !== undefined && payload.token_use !== "access") {
        continue;
      }
      const sub = typeof payload.sub === "string" ? payload.sub : "";
      const tid = typeof payload.tid === "string" ? payload.tid : "";
      const roles = Array.isArray(payload.roles) ? payload.roles.map(String) : [];
      if (!sub || !tid || !roles.length) {
        continue;
      }
      return { sub, tid, roles };
    } catch {
      continue;
    }
  }
  return null;
}

export function extractBearerToken(authorization: string | null): string | null {
  if (!authorization?.startsWith("Bearer ")) {
    return null;
  }
  const t = authorization.slice(7).trim();
  return t || null;
}

export type ApplyDeployaiJwtResult = { invalidToken: true } | undefined;

/**
 * When `DEPLOYAI_WEB_TRUST_JWT=1` and PEM is configured, set `x-deployai-role` and
 * `x-deployai-tenant` from a valid Bearer or access-token cookie (overrides client headers).
 *
 * If a Bearer or cookie **value is present** but no candidate verifies, returns `{ invalidToken: true }`
 * so middleware can **401** instead of falling through to spoofed `x-deployai-*` headers.
 */
export async function applyDeployaiAccessJwtToHeaders(
  authorization: string | null,
  cookieValue: string | null,
  headers: Headers,
): Promise<ApplyDeployaiJwtResult> {
  if (process.env.DEPLOYAI_WEB_TRUST_JWT !== "1") {
    return;
  }
  if (!process.env.DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM?.trim()) {
    return;
  }
  const bearer = extractBearerToken(authorization);
  const cookie = cookieValue?.trim() || null;
  const candidates: string[] = [];
  if (bearer) {
    candidates.push(bearer);
  }
  if (cookie && cookie !== bearer) {
    candidates.push(cookie);
  }
  if (!candidates.length) {
    return;
  }
  let claims: DeployaiAccessClaims | null = null;
  for (const t of candidates) {
    const c = await verifyDeployaiAccessJwt(t);
    if (c) {
      claims = c;
      break;
    }
  }
  if (!claims) {
    return { invalidToken: true };
  }
  const role = v1RoleFromJwtRoles(claims.roles);
  if (!role) {
    return { invalidToken: true };
  }
  headers.set("x-deployai-role", role);
  headers.set("x-deployai-tenant", claims.tid);
}
