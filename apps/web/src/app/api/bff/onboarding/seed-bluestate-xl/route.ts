import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpStartBluestateXlSeed } from "@/lib/internal/seed-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

/**
 * Onboarding wizard — load BlueState-XL 5-year stress-test fixture. Mirrors
 * the seed-bluestate route; one CP call runs the procedural seed; 409 means
 * the engagement already exists for this tenant.
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

  let body: { force?: boolean };
  try {
    body = (await req.json()) as typeof body;
  } catch {
    body = {};
  }
  const force = body.force === true;

  try {
    const result = await cpStartBluestateXlSeed(tid, { force });
    if (result.status === "ok") {
      return NextResponse.json(result.body, { status: 200 });
    }
    if (result.status === "conflict") {
      return NextResponse.json(
        {
          error: "already_seeded",
          engagement_id: result.body.detail.engagement_id,
        },
        { status: 409 },
      );
    }
    return new NextResponse(result.message || "Seed failed", { status: result.code || 502 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
