/**
 * Control-plane per-tenant LLM config client (Sprint 1).
 *
 * Wraps `GET /internal/v1/tenants/{tenant_id}/llm-config` (returns null
 * when no row exists — caller renders "use env default") and
 * `PUT /internal/v1/tenants/{tenant_id}/llm-config` (upsert).
 *
 * The CP response never includes the raw API key — only
 * `api_key_masked` + `has_api_key`. The form keeps the key as a
 * write-only field.
 */
import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

export type TenantLlmConfig = {
  tenant_id: string;
  provider: string;
  model_name: string | null;
  api_key_masked: string | null;
  has_api_key: boolean;
  secondary_provider: string | null;
  secondary_model_name: string | null;
  secondary_api_key_masked: string | null;
  has_secondary_api_key: boolean;
  updated_at: string;
};

export type TenantLlmConfigWrite = {
  provider: string;
  model_name?: string | null;
  api_key?: string | null;
  secondary_provider?: string | null;
  secondary_model_name?: string | null;
  secondary_api_key?: string | null;
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

export async function cpGetTenantLlmConfig(tenantId: string): Promise<TenantLlmConfig | null> {
  const url = `${cpBase()}/internal/v1/tenants/${encodeURIComponent(tenantId)}/llm-config`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp llm-config get ${r.status}: ${await r.text()}`);
  }
  const body = (await r.json()) as TenantLlmConfig | null;
  return body;
}

export async function cpPutTenantLlmConfig(
  tenantId: string,
  body: TenantLlmConfigWrite,
): Promise<TenantLlmConfig> {
  const url = `${cpBase()}/internal/v1/tenants/${encodeURIComponent(tenantId)}/llm-config`;
  const r = await fetch(url, {
    method: "PUT",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp llm-config put ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as TenantLlmConfig;
}
