import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpSnoozeTemporalInsight } from "@/lib/internal/insights-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string; insightId: string }> };

export async function POST(request: NextRequest, ctx: Ctx) {
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
  const { engagementId, insightId } = await ctx.params;
  const tid = actor.tenantId!.trim();
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid json body" }, { status: 400 });
  }
  const days = parseDays(body);
  if (days === null) {
    return NextResponse.json(
      { error: "days must be an integer between 1 and 90" },
      { status: 400 },
    );
  }
  try {
    const snooze = await cpSnoozeTemporalInsight(tid, engagementId, insightId, { days });
    return NextResponse.json({ snooze, source: "cp" }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}

function parseDays(raw: unknown): number | null {
  if (raw === null || typeof raw !== "object") return null;
  const days = (raw as { days?: unknown }).days;
  if (typeof days !== "number" || !Number.isInteger(days) || days < 1 || days > 90) {
    return null;
  }
  return days;
}
