/**
 * Control-plane deployment-matrix API (internal key). The matrix property
 * graph lives in Postgres via the CP `/internal/v1/engagements/{id}/matrix`
 * internal API. See `docs/product/deployment-matrix-model.md`.
 */
import type { MatrixEdge, MatrixNode } from "@/lib/bff/matrix-types";

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

function matrixUrl(tenantId: string, engagementId: string, leaf: "nodes" | "edges"): string {
  return (
    `${cpBase()}/internal/v1/engagements/${encodeURIComponent(engagementId)}/matrix/${leaf}` +
    `?tenant_id=${encodeURIComponent(tenantId)}`
  );
}

export async function cpListMatrixNodes(
  tenantId: string,
  engagementId: string,
): Promise<MatrixNode[]> {
  const r = await fetch(matrixUrl(tenantId, engagementId, "nodes"), {
    method: "GET",
    headers: cpHeaders(),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp matrix nodes list ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as MatrixNode[];
}

export async function cpListMatrixEdges(
  tenantId: string,
  engagementId: string,
): Promise<MatrixEdge[]> {
  const r = await fetch(matrixUrl(tenantId, engagementId, "edges"), {
    method: "GET",
    headers: cpHeaders(),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp matrix edges list ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as MatrixEdge[];
}
