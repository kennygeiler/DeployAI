/**
 * Control-plane Slack channel-intake client (Wave 5 SL1).
 *
 * Wraps `/internal/v1/slack/channel-mappings` (+ `/revoke`),
 * `/internal/v1/slack/pending-channels`, and `/internal/v1/slack/flush`.
 * A mapping is the consent record: only mapped channels' messages are
 * ever stored; pending channels are bot-invited-but-unmapped (id + name
 * only, no content).
 */
import { z } from "zod";

import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

export const zSlackChannelMapping = z.object({
  id: z.string(),
  tenant_id: z.string(),
  channel_id: z.string(),
  channel_name: z.string(),
  engagement_id: z.string(),
  created_by: z.string().nullable(),
  created_at: z.string(),
  revoked_at: z.string().nullable(),
});

export type SlackChannelMapping = z.infer<typeof zSlackChannelMapping>;

export const zSlackPendingChannel = z.object({
  id: z.string(),
  channel_id: z.string(),
  channel_name: z.string(),
  first_seen_at: z.string(),
});

export type SlackPendingChannel = z.infer<typeof zSlackPendingChannel>;

export type SlackChannelMappingCreate = {
  channel_id: string;
  channel_name?: string;
  engagement_id: string;
  created_by?: string | null;
};

function cpHeaders(): Record<string, string> {
  const key = getControlPlaneInternalKey();
  if (!key) {
    throw new Error("DEPLOYAI_INTERNAL_API_KEY not set");
  }
  return { "X-DeployAI-Internal-Key": key };
}

function cpBase(): string {
  const base = getControlPlaneBaseUrl()?.replace(/\/$/, "");
  if (!base) {
    throw new Error("DEPLOYAI_CONTROL_PLANE_URL not set");
  }
  return base;
}

export async function cpListSlackChannelMappings(tenantId: string): Promise<SlackChannelMapping[]> {
  const url = `${cpBase()}/internal/v1/slack/channel-mappings?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp slack mappings list ${r.status}: ${await r.text()}`);
  }
  return z.array(zSlackChannelMapping).parse(await r.json());
}

export async function cpCreateSlackChannelMapping(
  tenantId: string,
  body: SlackChannelMappingCreate,
): Promise<SlackChannelMapping> {
  const url = `${cpBase()}/internal/v1/slack/channel-mappings?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, {
    method: "POST",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp slack mapping create ${r.status}: ${await r.text()}`);
  }
  return zSlackChannelMapping.parse(await r.json());
}

export async function cpRevokeSlackChannelMapping(
  tenantId: string,
  mappingId: string,
): Promise<SlackChannelMapping> {
  const url = `${cpBase()}/internal/v1/slack/channel-mappings/${encodeURIComponent(mappingId)}/revoke?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, { method: "POST", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp slack mapping revoke ${r.status}: ${await r.text()}`);
  }
  return zSlackChannelMapping.parse(await r.json());
}

export async function cpListSlackPendingChannels(tenantId: string): Promise<SlackPendingChannel[]> {
  const url = `${cpBase()}/internal/v1/slack/pending-channels?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp slack pending channels ${r.status}: ${await r.text()}`);
  }
  return z.array(zSlackPendingChannel).parse(await r.json());
}
