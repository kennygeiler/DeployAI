import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";
import { cpDeleteWebhook, cpUpdateWebhook, type WebhookUpdate } from "@/lib/internal/webhooks-cp";

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

export async function PUT(req: Request, { params }: { params: Promise<{ webhookId: string }> }) {
  const g = await guard();
  if ("error" in g) return g.error;
  const { webhookId } = await params;
  let body: WebhookUpdate;
  try {
    body = (await req.json()) as WebhookUpdate;
  } catch {
    return new NextResponse("Bad Request: invalid JSON", { status: 400 });
  }
  try {
    const updated = await cpUpdateWebhook(g.tid, webhookId, body);
    return NextResponse.json({ webhook: updated }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}

export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ webhookId: string }> },
) {
  const g = await guard();
  if ("error" in g) return g.error;
  const { webhookId } = await params;
  try {
    await cpDeleteWebhook(g.tid, webhookId);
    return new NextResponse(null, { status: 204 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
