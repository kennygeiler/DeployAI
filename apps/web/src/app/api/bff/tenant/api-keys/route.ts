import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import {
  type ApiKeyMintBody,
  cpListTenantApiKeys,
  cpMintTenantApiKey,
} from "@/lib/internal/api-keys-cp";
import { emitTenantAuditEventBackground } from "@/lib/internal/audit-emit";
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
    const rows = await cpListTenantApiKeys(g.tid);
    return NextResponse.json({ api_keys: rows }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}

export async function POST(req: Request) {
  const g = await guard();
  if ("error" in g) return g.error;
  let body: ApiKeyMintBody;
  try {
    body = (await req.json()) as ApiKeyMintBody;
  } catch {
    return new NextResponse("Bad Request: invalid JSON", { status: 400 });
  }
  if (
    !body ||
    typeof body.name !== "string" ||
    !body.name.trim() ||
    typeof body.engagement_id !== "string" ||
    !body.engagement_id.trim()
  ) {
    return new NextResponse("Bad Request: name and engagement_id are required", { status: 400 });
  }
  try {
    const minted = await cpMintTenantApiKey(g.tid, {
      name: body.name,
      engagement_id: body.engagement_id,
      ...(Array.isArray(body.scopes) ? { scopes: body.scopes } : {}),
    });
    emitTenantAuditEventBackground(
      g.tid,
      await getActorIdFromHeaders(),
      "tenant.api_key.created",
      `minted MCP api key ${minted.api_key.name}`,
      { api_key_id: minted.api_key.id, engagement_id: minted.api_key.engagement_id },
      minted.api_key.id,
    );
    return NextResponse.json(minted, { status: 201 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
