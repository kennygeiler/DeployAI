/**
 * Control-plane engagement-timeline API (internal key). Read-only view over
 * `canonical_memory_events` for one engagement, ordered chronologically.
 */
import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

export type TimelineEvent = {
  id: string;
  occurred_at: string;
  event_type: string;
  source_ref: string | null;
  summary: string;
};

export type TimelineResponse = {
  events: TimelineEvent[];
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

export async function cpListTimeline(
  tenantId: string,
  engagementId: string,
  days: number,
): Promise<TimelineResponse> {
  const url =
    `${cpBase()}/internal/v1/engagements/${encodeURIComponent(engagementId)}/timeline` +
    `?tenant_id=${encodeURIComponent(tenantId)}&days=${encodeURIComponent(String(days))}`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp engagement timeline ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as TimelineResponse;
}
