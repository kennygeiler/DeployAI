import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";
import { cpCreateTenantUser } from "@/lib/internal/tenant-users-cp";

/**
 * Sprint 1 inc 2 — create an AppUser via the internal admin key (no
 * SCIM token). Used by the first-run onboarding wizard so the team can
 * seed its first member without running an IdP. SCIM stays the
 * supported production provisioning path.
 *
 * Reuses the same `canonical:read` gate as the rest of the
 * strategist-surface BFF (V1 self-hosted single-team install — see the
 * /llm-config BFF note). Promote to admin-tier when Sprint 3 adds
 * customer_admin-only flows.
 */

export async function POST(req: Request) {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const d = decideSync(actor, "canonical:read", { kind: "canonical_memory" });
  if (!d.allow) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  const cpMisconfigured = strategistQueueBffCpMisconfiguredResponse(actor.tenantId);
  if (cpMisconfigured) {
    return cpMisconfigured;
  }
  const tid = actor.tenantId!.trim();
  let body: {
    user_name?: string;
    email?: string | null;
    given_name?: string | null;
    family_name?: string | null;
  };
  try {
    body = (await req.json()) as typeof body;
  } catch {
    return new NextResponse("Bad Request: invalid JSON", { status: 400 });
  }
  const userName = typeof body.user_name === "string" ? body.user_name.trim() : "";
  if (!userName) {
    return new NextResponse("Bad Request: user_name is required", { status: 400 });
  }
  try {
    const user = await cpCreateTenantUser(tid, {
      user_name: userName,
      email: body.email ?? null,
      given_name: body.given_name ?? null,
      family_name: body.family_name ?? null,
    });
    return NextResponse.json({ user }, { status: 201 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
