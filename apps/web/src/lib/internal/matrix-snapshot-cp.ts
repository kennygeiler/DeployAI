import { z } from "zod";

import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

/**
 * Phase F3.c — historical matrix snapshot client. Pairs with the F3.b CP
 * endpoint `GET /internal/v1/engagements/{id}/matrix-snapshot?at=YYYY-MM-DD`
 * which returns the nearest-prior snapshot. See `docs/design/timeline-ledger.md`.
 */

export const AT_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

const zMatrixNode = z.object({
  id: z.string(),
  engagement_id: z.string(),
  node_type: z.string(),
  title: z.string(),
  identity_node_id: z.string().nullable(),
  attributes: z.record(z.string(), z.unknown()),
  status: z.string().nullable(),
  evidence_event_ids: z.array(z.string()),
  created_at: z.string(),
  updated_at: z.string(),
});

const zMatrixEdge = z.object({
  id: z.string(),
  engagement_id: z.string(),
  edge_type: z.string(),
  from_node_id: z.string(),
  to_node_id: z.string(),
  attributes: z.record(z.string(), z.unknown()),
  evidence_event_ids: z.array(z.string()),
  created_at: z.string(),
  updated_at: z.string(),
});

export const zMatrixSnapshot = z.object({
  captured_at: z.string(),
  nodes: z.array(zMatrixNode),
  edges: z.array(zMatrixEdge),
});

export type MatrixSnapshot = z.infer<typeof zMatrixSnapshot>;

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

export async function cpGetMatrixSnapshot(
  tenantId: string,
  engagementId: string,
  at: string,
): Promise<MatrixSnapshot> {
  const qs = new URLSearchParams({ tenant_id: tenantId, at });
  const url =
    `${cpBase()}/internal/v1/engagements/${encodeURIComponent(engagementId)}/matrix-snapshot` +
    `?${qs.toString()}`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp matrix-snapshot get ${r.status}: ${await r.text()}`);
  }
  const raw: unknown = await r.json();
  return zMatrixSnapshot.parse(raw);
}
