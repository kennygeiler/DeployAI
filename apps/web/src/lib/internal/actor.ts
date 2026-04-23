import { headers } from "next/headers";

import type { AuthActor, V1Role } from "@deployai/authz";

function roleFromHeaders(h: Headers): V1Role | null {
  const r = h.get("x-deployai-role");
  if (r === "platform_admin" || r === "external_auditor" || r === "customer_admin") {
    return r;
  }
  if (r === "deployment_strategist" || r === "successor_strategist" || r === "customer_records_officer") {
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
  const role = roleFromHeaders(h);
  if (!role) {
    return null;
  }
  const tenant = h.get("x-deployai-tenant") ?? undefined;
  return { role, tenantId: tenant };
}
