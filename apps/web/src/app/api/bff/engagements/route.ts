import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpCreateEngagement, cpListEngagements } from "@/lib/internal/engagements-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

/**
 * Phase 1 — list the engagements for the actor's tenant. Backs the
 * engagement selector in the strategist shell (increment 4b).
 *
 * Sprint 1 inc 2 — POST adds create-engagement, used by the first-run
 * onboarding wizard (and any future "new engagement" UI).
 */

async function guard() {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return { error: new NextResponse("Unauthorized", { status: 401 }) } as const;
  }
  const d = decideSync(actor, "canonical:read", { kind: "canonical_memory" });
  if (!d.allow) {
    return { error: new NextResponse("Forbidden", { status: 403 }) } as const;
  }
  const cpMisconfigured = strategistQueueBffCpMisconfiguredResponse(actor.tenantId);
  if (cpMisconfigured) {
    return { error: cpMisconfigured } as const;
  }
  return { tid: actor.tenantId!.trim() } as const;
}

export async function GET() {
  const g = await guard();
  if ("error" in g) return g.error;
  try {
    const engagements = await cpListEngagements(g.tid);
    return NextResponse.json({ engagements, source: "cp" }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}

export async function POST(req: Request) {
  const g = await guard();
  if ("error" in g) return g.error;
  let body: { name?: string; customer_account?: string | null; current_phase?: string };
  try {
    body = (await req.json()) as typeof body;
  } catch {
    return new NextResponse("Bad Request: invalid JSON", { status: 400 });
  }
  const name = typeof body.name === "string" ? body.name.trim() : "";
  if (!name) {
    return new NextResponse("Bad Request: name is required", { status: 400 });
  }
  try {
    const engagement = await cpCreateEngagement(g.tid, {
      name,
      customer_account: body.customer_account ?? null,
      ...(body.current_phase ? { current_phase: body.current_phase } : {}),
    });
    return NextResponse.json({ engagement }, { status: 201 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
