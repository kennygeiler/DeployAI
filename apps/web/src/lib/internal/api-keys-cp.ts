/**
 * Control-plane tenant API-keys client (v2 Phase 4, scope-v2 §8).
 *
 * Wraps the CP routes that mint, list, and revoke ``tenant_api_keys`` for
 * the MCP inbound server. The mint response includes ``raw_key`` exactly
 * once — the BFF passes it through to the client so the settings UI can
 * flash it; subsequent reads see only the row metadata.
 */
import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

export type ApiKey = {
  id: string;
  tenant_id: string;
  engagement_id: string | null;
  name: string;
  scopes: string[];
  last_used_at: string | null;
  created_at: string;
  revoked_at: string | null;
};

export type ApiKeyMintResponse = {
  api_key: ApiKey;
  raw_key: string;
};

export type ApiKeyMintBody = {
  name: string;
  engagement_id: string;
  scopes?: string[];
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

export async function cpListTenantApiKeys(tenantId: string): Promise<ApiKey[]> {
  const url = `${cpBase()}/internal/v1/tenant/api-keys?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp api-keys list ${r.status}: ${await r.text()}`);
  }
  const body = (await r.json()) as { api_keys: ApiKey[] };
  return body.api_keys;
}

export async function cpMintTenantApiKey(
  tenantId: string,
  body: ApiKeyMintBody,
): Promise<ApiKeyMintResponse> {
  const url = `${cpBase()}/internal/v1/tenant/api-keys?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, {
    method: "POST",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp api-keys mint ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as ApiKeyMintResponse;
}

export async function cpRevokeTenantApiKey(tenantId: string, apiKeyId: string): Promise<void> {
  const url = `${cpBase()}/internal/v1/tenant/api-keys/${encodeURIComponent(apiKeyId)}?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, { method: "DELETE", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp api-keys revoke ${r.status}: ${await r.text()}`);
  }
}
