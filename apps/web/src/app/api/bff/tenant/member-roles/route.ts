import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import {
  cpCreateMemberRole,
  cpListMemberRoles,
  type MemberRoleCreate,
} from "@/lib/internal/member-roles-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

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
    const data = await cpListMemberRoles(g.tid);
    return NextResponse.json(data, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}

export async function POST(req: Request) {
  const g = await guard();
  if ("error" in g) return g.error;
  let body: MemberRoleCreate;
  try {
    body = (await req.json()) as MemberRoleCreate;
  } catch {
    return new NextResponse("Bad Request: invalid JSON", { status: 400 });
  }
  if (
    !body ||
    typeof body.name !== "string" ||
    !body.name.trim() ||
    typeof body.label !== "string" ||
    !body.label.trim()
  ) {
    return new NextResponse("Bad Request: name and label are required", { status: 400 });
  }
  try {
    const created = await cpCreateMemberRole(g.tid, {
      name: body.name,
      label: body.label,
      ...(typeof body.description === "string" ? { description: body.description } : {}),
    });
    return NextResponse.json({ role: created }, { status: 201 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
