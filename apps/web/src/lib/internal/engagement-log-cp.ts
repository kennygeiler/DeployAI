/**
 * Control-plane engagement-log API (internal key). The engagement log is
 * Postgres-backed via the CP `/internal/v1/engagements/{id}/log` API.
 */
import type { EngagementLogEntry } from "@/lib/bff/engagement-log-types";

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

function logUrl(tenantId: string, engagementId: string): string {
  return (
    `${cpBase()}/internal/v1/engagements/${encodeURIComponent(engagementId)}/log` +
    `?tenant_id=${encodeURIComponent(tenantId)}`
  );
}

export async function cpListEngagementLog(
  tenantId: string,
  engagementId: string,
): Promise<EngagementLogEntry[]> {
  const r = await fetch(logUrl(tenantId, engagementId), {
    method: "GET",
    headers: cpHeaders(),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp engagement-log list ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as EngagementLogEntry[];
}

export async function cpAddEngagementLogEntry(
  tenantId: string,
  engagementId: string,
  entry: { entry_kind: string; body: string; author: string | null },
): Promise<EngagementLogEntry> {
  const r = await fetch(logUrl(tenantId, engagementId), {
    method: "POST",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(entry),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp engagement-log add ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as EngagementLogEntry;
}
