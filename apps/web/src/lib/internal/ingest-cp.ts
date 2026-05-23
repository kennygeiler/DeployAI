/**
 * Control-plane ingestion API (internal key). Posts a single interaction
 * to the CP `/internal/v1/engagements/{id}/ingest` endpoint; the CP creates
 * a canonical_memory_events row (engagement-scoped). Phase 6.2 layers an
 * extraction agent on top that reads these events and proposes matrix
 * entities citing them. See `docs/product/deployment-matrix-model.md`.
 */
import type { IngestInteractionPayload, IngestedEvent } from "@/lib/bff/ingest-types";

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

export async function cpIngestInteraction(
  tenantId: string,
  engagementId: string,
  payload: IngestInteractionPayload,
): Promise<IngestedEvent> {
  const url =
    `${cpBase()}/internal/v1/engagements/${encodeURIComponent(engagementId)}/ingest` +
    `?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, {
    method: "POST",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp ingest ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as IngestedEvent;
}
