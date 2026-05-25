import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import { emitTenantAuditEventBackground } from "@/lib/internal/audit-emit";
import {
  cpCreateMemberRole,
  cpListMemberRoles,
  zMemberRoleCreate,
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
    const body = await cpListMemberRoles(g.tid);
    return NextResponse.json(body, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}

export async function POST(req: Request) {
  const g = await guard();
  if ("error" in g) return g.error;
  const raw: unknown = await req.json().catch(() => null);
  const parsed = zMemberRoleCreate.safeParse(raw);
  if (!parsed.success) {
    return new NextResponse("Bad Request: name and label are required", { status: 400 });
  }
  const body = parsed.data;
  const name = body.name.trim();
  const label = body.label.trim();
  if (!name || !label) {
    return new NextResponse("Bad Request: name and label are required", { status: 400 });
  }
  try {
    const created = await cpCreateMemberRole(g.tid, {
      name,
      label,
      ...(body.description !== undefined ? { description: body.description } : {}),
    });
    emitTenantAuditEventBackground(
      g.tid,
      await getActorIdFromHeaders(),
      "tenant.member_role.created",
      `created member role ${created.name}`,
      { role_id: created.id, name: created.name },
      created.id,
    );
    return NextResponse.json({ member_role: created }, { status: 201 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
