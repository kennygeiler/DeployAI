import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpCreateNodeType, cpListNodeTypes, zNodeTypeCreate } from "@/lib/internal/node-types-cp";
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
    const body = await cpListNodeTypes(g.tid);
    return NextResponse.json(body, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}

export async function POST(req: Request) {
  const g = await guard();
  if ("error" in g) return g.error;
  const raw: unknown = await req.json().catch(() => null);
  const parsed = zNodeTypeCreate.safeParse(raw);
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
    const created = await cpCreateNodeType(g.tid, {
      name,
      label,
      ...(body.color !== undefined ? { color: body.color } : {}),
      ...(body.description !== undefined ? { description: body.description } : {}),
    });
    return NextResponse.json({ node_type: created }, { status: 201 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
