import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpSeedBluestateScenario } from "@/lib/internal/seed-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

/**
 * Onboarding wizard — load BlueState demo scenario (Path B). One CP call runs
 * the full 26-week seed; the wizard redirects into the new engagement on 200,
 * surfaces an "already seeded" toast on 409.
 *
 * Reuses the same `canonical:read` gate as the rest of the onboarding
 * BFF (V1 self-hosted single-team install — see /tenant/users + /llm-config).
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
    const result = await cpSeedBluestateScenario(tid, { force });
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
