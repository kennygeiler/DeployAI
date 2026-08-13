import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpCreateEngagement, cpListEngagements } from "@/lib/internal/engagements-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";
import { DEMO_ENGAGEMENT_COOKIE } from "@/lib/tour/steps";

/**
 * Phase 1 — list the engagements for the actor's tenant. Backs the
 * engagement selector in the strategist shell (increment 4b).
 *
 * Sprint 1 inc 2 — POST adds create-engagement, used by the first-run
 * onboarding wizard (and any future "new engagement" UI).
 *
 * Guest-sandbox wave — demo_guest sessions see the seeded fixtures plus
 * their OWN per-visitor sandbox only (never other guests'). The role check
 * happens here (the CP internal API is key-authed and has no user identity);
 * the actual filtering runs CP-side in SQL via exclude_demo_sandboxes /
 * visible_sandbox_id. Non-demo roles are untouched and see everything.
 */

const UUID_SHAPE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

async function guard(): Promise<NextResponse | { tid: string; role: string }> {
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
  return { tid: actor.tenantId!.trim(), role: actor.role };
}

export async function GET(): Promise<NextResponse> {
  const g = await guard();
  if (g instanceof NextResponse) return g;
  let listOpts: Parameters<typeof cpListEngagements>[1];
  if (g.role === "demo_guest") {
    // The demo_engagement cookie names this visitor's sandbox. Validate the
    // shape before forwarding — a mangled cookie must degrade to "fixtures
    // only", not 422 the whole portfolio. A missing cookie (older CP, or a
    // session minted before this wave) also degrades to fixtures only.
    const raw = (await cookies()).get(DEMO_ENGAGEMENT_COOKIE)?.value?.trim();
    listOpts = {
      excludeDemoSandboxes: true,
      visibleSandboxId: raw && UUID_SHAPE.test(raw) ? raw : null,
    };
  }
  try {
    const engagements = await cpListEngagements(g.tid, listOpts);
    return NextResponse.json({ engagements, source: "cp" }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}

export async function POST(req: Request) {
  const g = await guard();
  if (g instanceof NextResponse) return g;
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
