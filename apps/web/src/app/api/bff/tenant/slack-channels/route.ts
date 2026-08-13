import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import { emitTenantAuditEventBackground } from "@/lib/internal/audit-emit";
import {
  cpCreateSlackChannelMapping,
  cpListSlackChannelMappings,
  cpListSlackPendingChannels,
} from "@/lib/internal/slack-intake-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

/**
 * Wave 5 SL1 — Slack channel → engagement mappings.
 *
 * GET lists the active mappings plus the pending (bot-invited, unmapped)
 * channels for the settings UI. POST creates a mapping — the consent
 * record that lets the CP store the channel's messages.
 *
 * Authz: reads gate `canonical:read` like the sibling config routes;
 * create gates `ingest:sync` (platform_admin / deployment_strategist /
 * fde) — mapping a channel starts ingestion, so it takes the ingest
 * permission, not just read.
 */

async function guard(action: "canonical:read" | "ingest:sync") {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return { error: new NextResponse("Unauthorized", { status: 401 }) } as const;
  }
  const d = decideSync(actor, action, {
    kind: "canonical_memory",
    tenantId: actor.tenantId,
  });
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
  const g = await guard("canonical:read");
  if ("error" in g) return g.error;
  try {
    const [mappings, pending] = await Promise.all([
      cpListSlackChannelMappings(g.tid),
      cpListSlackPendingChannels(g.tid),
    ]);
    return NextResponse.json({ mappings, pending }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}

export async function POST(req: Request) {
  const g = await guard("ingest:sync");
  if ("error" in g) return g.error;
  let body: { channel_id?: unknown; channel_name?: unknown; engagement_id?: unknown };
  try {
    body = (await req.json()) as typeof body;
  } catch {
    return new NextResponse("Bad Request: invalid JSON", { status: 400 });
  }
  const channelId = typeof body.channel_id === "string" ? body.channel_id.trim() : "";
  const engagementId = typeof body.engagement_id === "string" ? body.engagement_id.trim() : "";
  if (!channelId || !engagementId) {
    return new NextResponse("Bad Request: channel_id and engagement_id are required", {
      status: 400,
    });
  }
  const channelName = typeof body.channel_name === "string" ? body.channel_name.trim() : "";
  try {
    const actorId = await getActorIdFromHeaders();
    const created = await cpCreateSlackChannelMapping(g.tid, {
      channel_id: channelId,
      channel_name: channelName,
      engagement_id: engagementId,
      created_by: actorId,
    });
    emitTenantAuditEventBackground(
      g.tid,
      actorId,
      "tenant.slack_channel.mapped",
      `mapped Slack channel ${created.channel_name || created.channel_id} to engagement`,
      { channel_id: created.channel_id, engagement_id: created.engagement_id },
      created.id,
    );
    return NextResponse.json({ mapping: created }, { status: 201 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
