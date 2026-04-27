import { headers } from "next/headers";

import type { AuthActor, V1Role } from "@deployai/authz";

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
 * v1: derive the actor from request headers. Production replaces this with
 * session + IdP (Epic 2). Platform engineers use the header in private preview.
 */
export async function getActorFromHeaders(): Promise<AuthActor | null> {
  const h = await headers();
  let role = roleFromHeaders(h);
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
  const tenant = h.get("x-deployai-tenant") ?? undefined;
  return { role, tenantId: tenant };
}
