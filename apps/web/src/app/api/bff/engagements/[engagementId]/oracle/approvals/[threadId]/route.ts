import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import {
  cpPostOracleApprovalDecision,
  OracleApprovalNotFoundError,
  zOracleApprovalDecision,
} from "@/lib/internal/oracle-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string; threadId: string }> };

/**
 * Agent Kenny in-turn approval decision (pilot-refresh D4). Proxies the CP
 * resume endpoint: the paused LangGraph turn continues with the human's
 * approve/deny and the completed reply comes back as JSON (non-streaming,
 * matching the chat panel's existing JSON fallback tier).
 */
export async function POST(request: NextRequest, ctx: Ctx) {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const d = decideSync(actor, "canonical:read", {
    kind: "canonical_memory",
    tenantId: actor.tenantId,
  });
  if (!d.allow) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  const cpMisconfigured = strategistQueueBffCpMisconfiguredResponse(actor.tenantId);
  if (cpMisconfigured) {
    return cpMisconfigured;
  }
  const actorId = await getActorIdFromHeaders();
  if (!actorId) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const { engagementId, threadId } = await ctx.params;
  const tid = actor.tenantId!.trim();

  let raw: unknown;
  try {
    raw = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  const parsed = zOracleApprovalDecision.safeParse(raw);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "invalid request", detail: parsed.error.message.slice(0, 500) },
      { status: 400 },
    );
  }

  try {
    const result = await cpPostOracleApprovalDecision(
      tid,
      engagementId,
      actorId,
      threadId,
      parsed.data,
    );
    return NextResponse.json(result, { status: 200 });
  } catch (e) {
    if (e instanceof OracleApprovalNotFoundError) {
      return NextResponse.json({ error: "approval not found" }, { status: 404 });
    }
    return nextResponseFromStrategistCpFetchError(e);
  }
}
