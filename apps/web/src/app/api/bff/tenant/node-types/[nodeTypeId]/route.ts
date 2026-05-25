import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import { emitTenantAuditEventBackground } from "@/lib/internal/audit-emit";
import {
  cpDeleteNodeType,
  cpUpdateNodeType,
  zNodeTypeUpdate,
  type NodeTypeUpdate,
} from "@/lib/internal/node-types-cp";
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

export async function PUT(req: Request, { params }: { params: Promise<{ nodeTypeId: string }> }) {
  const g = await guard();
  if ("error" in g) return g.error;
  const { nodeTypeId } = await params;
  const raw: unknown = await req.json().catch(() => null);
  const parsed = zNodeTypeUpdate.safeParse(raw);
  if (!parsed.success) {
    return new NextResponse("Bad Request: invalid update payload", { status: 400 });
  }
  const body: NodeTypeUpdate = {};
  if (parsed.data.label !== undefined) {
    const label = parsed.data.label.trim();
    if (!label) {
      return new NextResponse("Bad Request: label must not be empty", { status: 400 });
    }
    body.label = label;
  }
  if (parsed.data.color !== undefined) body.color = parsed.data.color;
  if (parsed.data.description !== undefined) body.description = parsed.data.description;
  try {
    const updated = await cpUpdateNodeType(g.tid, nodeTypeId, body);
    emitTenantAuditEventBackground(
      g.tid,
      await getActorIdFromHeaders(),
      "tenant.node_type.updated",
      `updated node type ${updated.name}`,
      { node_type_id: nodeTypeId },
      nodeTypeId,
    );
    return NextResponse.json({ node_type: updated }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}

export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ nodeTypeId: string }> },
) {
  const g = await guard();
  if ("error" in g) return g.error;
  const { nodeTypeId } = await params;
  try {
    await cpDeleteNodeType(g.tid, nodeTypeId);
    emitTenantAuditEventBackground(
      g.tid,
      await getActorIdFromHeaders(),
      "tenant.node_type.deleted",
      `deleted node type ${nodeTypeId}`,
      { node_type_id: nodeTypeId },
      nodeTypeId,
    );
    return new NextResponse(null, { status: 204 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
