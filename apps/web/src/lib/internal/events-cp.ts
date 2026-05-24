/**
 * Control-plane batch event lookup (internal key). Backs the citation
 * drill-down panel: a small set of `canonical_memory_events` rows by id,
 * scoped to one engagement. Mirrors the timeline-cp shape.
 */
import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

export type CitationEvent = {
  id: string;
  occurred_at: string;
  event_type: string;
  source_ref: string | null;
  summary: string;
};

export type EventsResponse = {
  events: CitationEvent[];
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

export async function cpGetEventsByIds(
  tenantId: string,
  engagementId: string,
  ids: string[],
): Promise<EventsResponse> {
  const url =
    `${cpBase()}/internal/v1/engagements/${encodeURIComponent(engagementId)}/events` +
    `?tenant_id=${encodeURIComponent(tenantId)}` +
    `&ids=${encodeURIComponent(ids.join(","))}`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp engagement events ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as EventsResponse;
}
