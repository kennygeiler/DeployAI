/**
 * Control-plane global event-search API (internal key). Substring match
 * on `payload::text` across the tenant's canonical_memory_events. See
 * `services/control-plane/src/control_plane/api/routes/event_search.py`.
 */

import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

export type EventSearchHit = {
  id: string;
  engagement_id: string | null;
  occurred_at: string;
  event_type: string;
  source_ref: string | null;
  snippet: string;
};

export type EventSearchResponse = {
  results: EventSearchHit[];
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

export async function cpSearchEvents(
  tenantId: string,
  q: string,
  limit?: number,
): Promise<EventSearchResponse> {
  const params = new URLSearchParams({ q });
  if (limit !== undefined) {
    params.set("limit", String(limit));
  }
  const url =
    `${cpBase()}/internal/v1/tenants/${encodeURIComponent(tenantId)}/events/search` +
    `?${params.toString()}`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp event search ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as EventSearchResponse;
}
