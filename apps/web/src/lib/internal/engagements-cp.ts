/**
 * Control-plane engagements API (internal key). Engagement state lives in
 * Postgres via the CP `/internal/v1/engagements` internal API.
 */
import type { Engagement, EngagementMember } from "@/lib/bff/engagement-types";

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

export async function cpListEngagements(tenantId: string): Promise<Engagement[]> {
  const url = `${cpBase()}/internal/v1/engagements?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp engagements list ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as Engagement[];
}

export async function cpGetEngagement(tenantId: string, engagementId: string): Promise<Engagement> {
  const url =
    `${cpBase()}/internal/v1/engagements/${encodeURIComponent(engagementId)}` +
    `?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp engagement get ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as Engagement;
}

export async function cpListEngagementMembers(
  tenantId: string,
  engagementId: string,
): Promise<EngagementMember[]> {
  const url =
    `${cpBase()}/internal/v1/engagements/${encodeURIComponent(engagementId)}/members` +
    `?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp engagement members list ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as EngagementMember[];
}
