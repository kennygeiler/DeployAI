import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import {
  cpPostOracleChat,
  OracleBudgetExhaustedError,
  zOracleChatRequest,
} from "@/lib/internal/oracle-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string }> };

/**
 * Mr. Oracle chat — POST one user message, get one oracle reply.
 *
 * G1.a CP route currently returns JSON; the SSE proxy is held until G1.b's
 * streaming primitives are wired into the CP route. This handler is shaped
 * so the front-end can swap to streaming without a contract churn.
 */
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
  const actorId = await getActorIdFromHeaders();
  if (!actorId) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const { engagementId } = await ctx.params;
  const tid = actor.tenantId!.trim();

  let raw: unknown;
  try {
    raw = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  const parsed = zOracleChatRequest.safeParse(raw);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "invalid request", detail: parsed.error.message.slice(0, 500) },
      { status: 400 },
    );
  }

  try {
    const reply = await cpPostOracleChat(tid, engagementId, actorId, parsed.data);
    return NextResponse.json({ ...reply, source: "cp" }, { status: 200 });
  } catch (e) {
    if (e instanceof OracleBudgetExhaustedError) {
      return NextResponse.json(
        {
          error: "budget_exhausted",
          code: "oracle_daily_budget",
          source: "cp_error",
          userMessage: "Daily LLM budget reached. Try again tomorrow.",
          retry_after_iso: e.retryAfterIso,
        },
        { status: 429 },
      );
    }
    return nextResponseFromStrategistCpFetchError(e);
  }
}
