import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpAddEngagementMember } from "@/lib/internal/engagements-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string }> };

const MEMBER_ROLES = ["fde", "deployment_strategist", "biz_dev"];

/**
 * Phase 4 — engagement membership. POST assigns a tenant user to the
 * engagement with a team role (fde / deployment_strategist / biz_dev).
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
  const { engagementId } = await ctx.params;
  const tid = actor.tenantId!.trim();
  let parsed: { user_id?: unknown; email?: unknown; role?: unknown };
  try {
    parsed = (await request.json()) as typeof parsed;
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  const userId = typeof parsed.user_id === "string" ? parsed.user_id.trim() : "";
  const email = typeof parsed.email === "string" ? parsed.email.trim() : "";
  const role = typeof parsed.role === "string" ? parsed.role : "";
  if (!MEMBER_ROLES.includes(role)) {
    return NextResponse.json({ error: "a valid role is required" }, { status: 400 });
  }
  if ((userId === "") === (email === "")) {
    return NextResponse.json(
      { error: "exactly one of user_id or email is required" },
      { status: 400 },
    );
  }
  const cpBody: { role: string; user_id?: string; email?: string } = { role };
  if (userId) {
    cpBody.user_id = userId;
  } else {
    cpBody.email = email;
  }
  try {
    const member = await cpAddEngagementMember(tid, engagementId, cpBody);
    return NextResponse.json({ member, source: "cp" }, { status: 201 });
  } catch (e) {
    if (e instanceof Error && / 409:/.test(e.message)) {
      return NextResponse.json(
        {
          error: "conflict",
          code: "already_member",
          source: "cp_error",
          userMessage: "That user is already a member of this engagement.",
        },
        { status: 409 },
      );
    }
    return nextResponseFromStrategistCpFetchError(e);
  }
}
