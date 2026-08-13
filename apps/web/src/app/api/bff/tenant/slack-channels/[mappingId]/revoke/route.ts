import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import { emitTenantAuditEventBackground } from "@/lib/internal/audit-emit";
import { cpRevokeSlackChannelMapping } from "@/lib/internal/slack-intake-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ mappingId: string }> };

/**
 * Wave 5 SL1 — revoke a Slack channel → engagement mapping.
 *
 * Revoking withdraws consent: the CP discards the channel's unflushed
 * staged messages and stops staging new ones. Content already flushed
 * into canonical memory stays (the ledger is append-only). Gated
 * `ingest:sync` like mapping creation.
 */
export async function POST(_req: NextRequest, ctx: Ctx) {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const d = decideSync(actor, "ingest:sync", {
    kind: "canonical_memory",
    tenantId: actor.tenantId,
  });
  if (!d.allow) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  const cpMisconfigured = strategistQueueBffCpMisconfiguredResponse(actor.tenantId);
  if (cpMisconfigured) {
    return cpMisconfigured;
  }
  const tid = actor.tenantId!.trim();
  const { mappingId } = await ctx.params;
  try {
    const revoked = await cpRevokeSlackChannelMapping(tid, mappingId);
    emitTenantAuditEventBackground(
      tid,
      await getActorIdFromHeaders(),
      "tenant.slack_channel.revoked",
      `revoked Slack channel mapping ${revoked.channel_name || revoked.channel_id}`,
      { channel_id: revoked.channel_id, engagement_id: revoked.engagement_id },
      revoked.id,
    );
    return NextResponse.json({ mapping: revoked }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
