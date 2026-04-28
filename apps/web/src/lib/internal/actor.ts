import { cookies, headers } from "next/headers";

import type { AuthActor, V1Role } from "@deployai/authz";

import {
  accessTokenCookieNameFromEnv,
  extractBearerToken,
  verifyDeployaiAccessJwt,
  v1RoleFromJwtRoles,
} from "./deployai-access-jwt";

function roleFromHeaders(h: Headers): V1Role | null {
  const r = h.get("x-deployai-role");
  if (r === "platform_admin" || r === "external_auditor" || r === "customer_admin") {
    return r;
  }
  if (
    r === "deployment_strategist" ||
    r === "successor_strategist" ||
    r === "customer_records_officer"
  ) {
    return r;
  }
  return null;
}

/**
 * v1: derive the actor from JWT (when `DEPLOYAI_WEB_TRUST_JWT=1` + PEM), request headers,
 * or dev default. Hosted pilot: configure CP-issued access tokens; headers remain for edge/proxy.
 */
export async function getActorFromHeaders(): Promise<AuthActor | null> {
  const h = await headers();
  let role = roleFromHeaders(h);
  let tenant = h.get("x-deployai-tenant") ?? undefined;

  if (!role && process.env.DEPLOYAI_WEB_TRUST_JWT === "1") {
    const c = await cookies();
    const name = accessTokenCookieNameFromEnv();
    const token = extractBearerToken(h.get("authorization")) ?? c.get(name)?.value ?? null;
    if (token) {
      const claims = await verifyDeployaiAccessJwt(token);
      const r2 = claims ? v1RoleFromJwtRoles(claims.roles) : null;
      if (r2) {
        role = r2;
        tenant = claims!.tid;
      }
    }
  }

  if (
    !role &&
    process.env.NODE_ENV === "development" &&
    process.env.DEPLOYAI_DISABLE_DEV_STRATEGIST !== "1"
  ) {
    // Mirrors `middleware.ts`: some dev setups (and certain Next + fetch paths) do not
    // forward middleware-injected headers into `headers()` for Route Handlers. Defaulting
    // here keeps `/api/internal/strategist-activity` and BFF routes usable in `next dev`
    // without a browser extension. Disabled with `DEPLOYAI_DISABLE_DEV_STRATEGIST=1`.
    role = "deployment_strategist";
  }
  if (!role) {
    return null;
  }
  return { role, tenantId: tenant };
}
