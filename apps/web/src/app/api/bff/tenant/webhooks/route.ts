import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import { emitTenantAuditEventBackground } from "@/lib/internal/audit-emit";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";
import { cpCreateWebhook, cpListWebhooks, type WebhookWrite } from "@/lib/internal/webhooks-cp";

/**
 * Sprint 8 — per-tenant webhook subscriptions UI.
 *
 * List + create. The create response includes the plaintext secret one
 * time so the client can flash it; subsequent reads see only the
 * masked fingerprint.
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
    const rows = await cpListWebhooks(g.tid);
    return NextResponse.json({ webhooks: rows }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}

export async function POST(req: Request) {
  const g = await guard();
  if ("error" in g) return g.error;
  let body: WebhookWrite;
  try {
    body = (await req.json()) as WebhookWrite;
  } catch {
    return new NextResponse("Bad Request: invalid JSON", { status: 400 });
  }
  if (
    !body ||
    typeof body.name !== "string" ||
    !body.name.trim() ||
    typeof body.url !== "string" ||
    !body.url.trim()
  ) {
    return new NextResponse("Bad Request: name and url are required", { status: 400 });
  }
  if (!Array.isArray(body.events)) {
    return new NextResponse("Bad Request: events must be an array", { status: 400 });
  }
  try {
    const created = await cpCreateWebhook(g.tid, {
      name: body.name,
      url: body.url,
      events: body.events,
      ...(body.secret ? { secret: body.secret } : {}),
      ...(typeof body.active === "boolean" ? { active: body.active } : {}),
    });
    emitTenantAuditEventBackground(
      g.tid,
      await getActorIdFromHeaders(),
      "tenant.webhook.created",
      `created webhook ${created.name}`,
      { webhook_id: created.id, events: created.events },
      created.id,
    );
    return NextResponse.json({ webhook: created }, { status: 201 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
