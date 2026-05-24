/**
 * Control-plane per-tenant webhooks client (Sprint 8).
 *
 * Wraps `GET/POST/PUT/DELETE /internal/v1/webhooks` and the
 * `/internal/v1/webhooks/{id}/deliveries` listing. The CP responses
 * never include the raw secret except on create — the form flashes it
 * once and never echoes it again.
 */
import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

export type Webhook = {
  id: string;
  tenant_id: string;
  name: string;
  url: string;
  events: string[];
  active: boolean;
  secret_masked: string | null;
  has_secret: boolean;
  created_at: string;
  updated_at: string;
};

export type WebhookCreateResponse = Webhook & { secret: string | null };

export type WebhookWrite = {
  name: string;
  url: string;
  events: string[];
  secret?: string | null;
  active?: boolean;
};

export type WebhookUpdate = {
  name?: string;
  url?: string;
  events?: string[];
  active?: boolean;
};

export type WebhookDelivery = {
  id: string;
  webhook_id: string;
  event_name: string;
  payload: Record<string, unknown>;
  status: "pending" | "succeeded" | "failed";
  response_status: number | null;
  error: string | null;
  attempts: number;
  created_at: string;
  completed_at: string | null;
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

export async function cpListWebhooks(tenantId: string): Promise<Webhook[]> {
  const url = `${cpBase()}/internal/v1/webhooks?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp webhooks list ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as Webhook[];
}

export async function cpCreateWebhook(
  tenantId: string,
  body: WebhookWrite,
): Promise<WebhookCreateResponse> {
  const url = `${cpBase()}/internal/v1/webhooks?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, {
    method: "POST",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp webhooks create ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as WebhookCreateResponse;
}

export async function cpUpdateWebhook(
  tenantId: string,
  webhookId: string,
  body: WebhookUpdate,
): Promise<Webhook> {
  const url = `${cpBase()}/internal/v1/webhooks/${encodeURIComponent(webhookId)}?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, {
    method: "PUT",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp webhooks update ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as Webhook;
}

export async function cpDeleteWebhook(tenantId: string, webhookId: string): Promise<void> {
  const url = `${cpBase()}/internal/v1/webhooks/${encodeURIComponent(webhookId)}?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, { method: "DELETE", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp webhooks delete ${r.status}: ${await r.text()}`);
  }
}

export async function cpListDeliveries(
  tenantId: string,
  webhookId: string,
  limit = 50,
): Promise<WebhookDelivery[]> {
  const url = `${cpBase()}/internal/v1/webhooks/${encodeURIComponent(webhookId)}/deliveries?tenant_id=${encodeURIComponent(tenantId)}&limit=${limit}`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp webhooks deliveries ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as WebhookDelivery[];
}
