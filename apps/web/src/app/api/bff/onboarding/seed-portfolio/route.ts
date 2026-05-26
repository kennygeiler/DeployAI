import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpStartPortfolioSeed } from "@/lib/internal/seed-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

/**
 * Onboarding wizard — load DeployAI Portfolio fixture (5 engagements × 26
 * weeks under one tenant). Cross-engagement isolation stress fixture for
 * Agent Kenny.
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
    const result = await cpStartPortfolioSeed(tid, { force });
    if (result.status === "ok") {
      return NextResponse.json(result.body, { status: 200 });
    }
    if (result.status === "conflict") {
      return NextResponse.json(
        {
          error: "already_seeded",
          engagement_ids: result.body.detail.engagement_ids,
        },
        { status: 409 },
      );
    }
    return new NextResponse(result.message || "Seed failed", { status: result.code || 502 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
