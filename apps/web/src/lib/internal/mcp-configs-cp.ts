/**
 * Control-plane outbound-MCP config client (v2 Phase 5 Wave 3H).
 *
 * Wraps the Wave 2E CRUD routes + the Wave 2E OAuth start/callback +
 * Wave 3H kill-switch routes. The raw token never crosses this layer
 * inbound (the CP write paths take it on create/patch); reads only
 * surface ``has_auth_token`` so the UI can flag connectors that still
 * need an OAuth handshake.
 */
import { z } from "zod";

import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

export const CONNECTOR_KINDS = ["slack", "linear", "gdrive", "notion", "github"] as const;
export type ConnectorKind = (typeof CONNECTOR_KINDS)[number];

export const McpTransports = ["http_sse"] as const;
export type McpTransport = (typeof McpTransports)[number];

export const TenantMcpConfigReadSchema = z.object({
  id: z.string(),
  tenant_id: z.string(),
  name: z.string(),
  connector_kind: z.enum(CONNECTOR_KINDS),
  transport: z.enum(McpTransports),
  endpoint: z.string(),
  has_auth_token: z.boolean(),
  allowed_tools: z.array(z.string()).nullable(),
  enabled: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type TenantMcpConfigRead = z.infer<typeof TenantMcpConfigReadSchema>;

export const KillSwitchSchema = z.object({ disabled: z.boolean() });
export type KillSwitchState = z.infer<typeof KillSwitchSchema>;

export const OAuthStartResponseSchema = z.object({
  authorization_url: z.string(),
  state: z.string(),
});
export type OAuthStartResponse = z.infer<typeof OAuthStartResponseSchema>;

export type TenantMcpConfigCreate = {
  name: string;
  connector_kind: ConnectorKind;
  endpoint: string;
  transport?: McpTransport;
  auth_token?: string | null;
  allowed_tools?: string[] | null;
  enabled?: boolean;
};

export type TenantMcpConfigPatch = {
  name?: string;
  endpoint?: string;
  transport?: McpTransport;
  auth_token?: string | null;
  allowed_tools?: string[] | null;
  enabled?: boolean;
};

function cpHeaders(actorId?: string | null): Record<string, string> {
  const key = getControlPlaneInternalKey();
  if (!key) throw new Error("DEPLOYAI_INTERNAL_API_KEY not set");
  const h: Record<string, string> = { "X-DeployAI-Internal-Key": key };
  if (actorId && actorId.trim()) h["X-DeployAI-Actor-Id"] = actorId.trim();
  return h;
}

function cpBase(): string {
  const base = getControlPlaneBaseUrl()?.replace(/\/$/, "");
  if (!base) throw new Error("DEPLOYAI_CONTROL_PLANE_URL not set");
  return base;
}

function cpRoot(tenantId: string): string {
  return `${cpBase()}/internal/v1/tenants/${encodeURIComponent(tenantId)}/mcp_configs`;
}

export async function cpListMcpConfigs(tenantId: string): Promise<TenantMcpConfigRead[]> {
  const r = await fetch(cpRoot(tenantId), {
    method: "GET",
    headers: cpHeaders(),
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`cp mcp_configs list ${r.status}: ${await r.text()}`);
  const body = (await r.json()) as unknown;
  return z.array(TenantMcpConfigReadSchema).parse(body);
}

export async function cpCreateMcpConfig(
  tenantId: string,
  body: TenantMcpConfigCreate,
  actorId?: string | null,
): Promise<TenantMcpConfigRead> {
  const r = await fetch(cpRoot(tenantId), {
    method: "POST",
    headers: { ...cpHeaders(actorId), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`cp mcp_configs create ${r.status}: ${await r.text()}`);
  return TenantMcpConfigReadSchema.parse(await r.json());
}

export async function cpGetMcpConfig(
  tenantId: string,
  configId: string,
): Promise<TenantMcpConfigRead> {
  const r = await fetch(`${cpRoot(tenantId)}/${encodeURIComponent(configId)}`, {
    method: "GET",
    headers: cpHeaders(),
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`cp mcp_configs get ${r.status}: ${await r.text()}`);
  return TenantMcpConfigReadSchema.parse(await r.json());
}

export async function cpPatchMcpConfig(
  tenantId: string,
  configId: string,
  patch: TenantMcpConfigPatch,
  actorId?: string | null,
): Promise<TenantMcpConfigRead> {
  const r = await fetch(`${cpRoot(tenantId)}/${encodeURIComponent(configId)}`, {
    method: "PATCH",
    headers: { ...cpHeaders(actorId), "Content-Type": "application/json" },
    body: JSON.stringify(patch),
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`cp mcp_configs patch ${r.status}: ${await r.text()}`);
  return TenantMcpConfigReadSchema.parse(await r.json());
}

export async function cpDeleteMcpConfig(
  tenantId: string,
  configId: string,
  actorId?: string | null,
): Promise<void> {
  const r = await fetch(`${cpRoot(tenantId)}/${encodeURIComponent(configId)}`, {
    method: "DELETE",
    headers: cpHeaders(actorId),
    cache: "no-store",
  });
  if (!r.ok && r.status !== 204) {
    throw new Error(`cp mcp_configs delete ${r.status}: ${await r.text()}`);
  }
}

export async function cpStartMcpOAuth(
  tenantId: string,
  configId: string,
  redirectUri: string,
  actorId?: string | null,
): Promise<OAuthStartResponse> {
  const r = await fetch(`${cpRoot(tenantId)}/${encodeURIComponent(configId)}/oauth/start`, {
    method: "POST",
    headers: { ...cpHeaders(actorId), "Content-Type": "application/json" },
    body: JSON.stringify({ redirect_uri: redirectUri }),
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`cp mcp_configs oauth/start ${r.status}: ${await r.text()}`);
  return OAuthStartResponseSchema.parse(await r.json());
}

export async function cpFinishMcpOAuth(
  tenantId: string,
  configId: string,
  code: string,
  state: string,
  actorId?: string | null,
): Promise<TenantMcpConfigRead> {
  const r = await fetch(`${cpRoot(tenantId)}/${encodeURIComponent(configId)}/oauth/callback`, {
    method: "POST",
    headers: { ...cpHeaders(actorId), "Content-Type": "application/json" },
    body: JSON.stringify({ code, state }),
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`cp mcp_configs oauth/callback ${r.status}: ${await r.text()}`);
  return TenantMcpConfigReadSchema.parse(await r.json());
}

// ---------------------------------------------------------------------------
// Kill-switch (Wave 3H new CP route).
// ---------------------------------------------------------------------------

function cpKillSwitchUrl(tenantId: string): string {
  return `${cpBase()}/internal/v1/tenants/${encodeURIComponent(tenantId)}/mcp_killswitch`;
}

export async function cpGetMcpKillSwitch(tenantId: string): Promise<KillSwitchState> {
  const r = await fetch(cpKillSwitchUrl(tenantId), {
    method: "GET",
    headers: cpHeaders(),
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`cp mcp_killswitch get ${r.status}: ${await r.text()}`);
  return KillSwitchSchema.parse(await r.json());
}

export async function cpSetMcpKillSwitch(
  tenantId: string,
  disabled: boolean,
  actorId?: string | null,
): Promise<KillSwitchState> {
  const r = await fetch(cpKillSwitchUrl(tenantId), {
    method: "POST",
    headers: { ...cpHeaders(actorId), "Content-Type": "application/json" },
    body: JSON.stringify({ disabled }),
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`cp mcp_killswitch set ${r.status}: ${await r.text()}`);
  return KillSwitchSchema.parse(await r.json());
}
