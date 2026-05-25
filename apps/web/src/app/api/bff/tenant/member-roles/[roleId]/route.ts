import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import { emitTenantAuditEventBackground } from "@/lib/internal/audit-emit";
import {
  cpDeleteMemberRole,
  cpUpdateMemberRole,
  zMemberRoleUpdate,
  type MemberRoleUpdate,
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

export async function PUT(req: Request, { params }: { params: Promise<{ roleId: string }> }) {
  const g = await guard();
  if ("error" in g) return g.error;
  const { roleId } = await params;
  const raw: unknown = await req.json().catch(() => null);
  const parsed = zMemberRoleUpdate.safeParse(raw);
  if (!parsed.success) {
    return new NextResponse("Bad Request: invalid update payload", { status: 400 });
  }
  const body: MemberRoleUpdate = {};
  if (parsed.data.label !== undefined) {
    const label = parsed.data.label.trim();
    if (!label) {
      return new NextResponse("Bad Request: label must not be empty", { status: 400 });
    }
    body.label = label;
  }
  if (parsed.data.description !== undefined) body.description = parsed.data.description;
  try {
    const updated = await cpUpdateMemberRole(g.tid, roleId, body);
    emitTenantAuditEventBackground(
      g.tid,
      await getActorIdFromHeaders(),
      "tenant.member_role.updated",
      `updated member role ${updated.name}`,
      { role_id: roleId },
      roleId,
    );
    return NextResponse.json({ member_role: updated }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}

export async function DELETE(_req: Request, { params }: { params: Promise<{ roleId: string }> }) {
  const g = await guard();
  if ("error" in g) return g.error;
  const { roleId } = await params;
  try {
    await cpDeleteMemberRole(g.tid, roleId);
    emitTenantAuditEventBackground(
      g.tid,
      await getActorIdFromHeaders(),
      "tenant.member_role.deleted",
      `deleted member role ${roleId}`,
      { role_id: roleId },
      roleId,
    );
    return new NextResponse(null, { status: 204 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
