/**
 * Control-plane strategist queue APIs (internal key). Used when
 * {@link strategistQueuesUseControlPlane} is true.
 */
import type {
  ActionQueueItem,
  SolidificationQueueRow,
  ValidationQueueRow,
} from "@/lib/bff/strategist-queues-store";

import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

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

export async function cpListActionQueue(tenantId: string): Promise<ActionQueueItem[]> {
  const url = `${cpBase()}/internal/v1/strategist/action-queue-items?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp action-queue list ${r.status}: ${await r.text()}`);
  }
  const rows = (await r.json()) as ActionQueueItem[];
  return rows;
}

export async function cpBulkAppendActionQueue(
  tenantId: string,
  items: ActionQueueItem[],
): Promise<ActionQueueItem[]> {
  const url = `${cpBase()}/internal/v1/strategist/action-queue-items/bulk?tenant_id=${encodeURIComponent(tenantId)}`;
  const payload = {
    items: items.map((it) => ({
      id: it.id,
      priority: it.priority,
      phase: it.phase,
      description: it.description,
      status: it.status,
      claimed_by: it.claimed_by,
      updated_at: it.updated_at,
      source: it.source,
      evidence_node_ids: it.evidence_node_ids ?? [],
    })),
  };
  const r = await fetch(url, {
    method: "POST",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp action-queue bulk ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as ActionQueueItem[];
}

export async function cpPatchActionQueueItem(
  tenantId: string,
  itemId: string,
  body: {
    status: string;
    claimed_by?: string | null;
    resolution_reason?: string | null;
    evidence_event_ids?: string[] | null;
  },
): Promise<ActionQueueItem> {
  const url = `${cpBase()}/internal/v1/strategist/action-queue-items/${encodeURIComponent(itemId)}?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, {
    method: "PATCH",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp action-queue patch ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as ActionQueueItem;
}

export async function cpListValidationQueue(tenantId: string): Promise<ValidationQueueRow[]> {
  const url = `${cpBase()}/internal/v1/strategist/validation-queue-items?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp validation-queue list ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as ValidationQueueRow[];
}

export async function cpPatchValidationQueueItem(
  tenantId: string,
  itemId: string,
  state: ValidationQueueRow["state"],
): Promise<ValidationQueueRow> {
  const url = `${cpBase()}/internal/v1/strategist/validation-queue-items/${encodeURIComponent(itemId)}?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, {
    method: "PATCH",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ state }),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp validation-queue patch ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as ValidationQueueRow;
}

export async function cpListSolidificationQueue(
  tenantId: string,
): Promise<SolidificationQueueRow[]> {
  const url = `${cpBase()}/internal/v1/strategist/solidification-queue-items?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp solidification-queue list ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as SolidificationQueueRow[];
}

export async function cpPatchSolidificationQueueItem(
  tenantId: string,
  itemId: string,
  state: SolidificationQueueRow["state"],
): Promise<SolidificationQueueRow> {
  const url = `${cpBase()}/internal/v1/strategist/solidification-queue-items/${encodeURIComponent(itemId)}?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, {
    method: "PATCH",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ state }),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp solidification-queue patch ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as SolidificationQueueRow;
}
