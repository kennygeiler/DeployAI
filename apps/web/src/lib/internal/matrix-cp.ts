/**
 * Control-plane deployment-matrix API (internal key). The matrix property
 * graph lives in Postgres via the CP `/internal/v1/engagements/{id}/matrix`
 * internal API. See `docs/product/deployment-matrix-model.md`.
 */
import type { MatrixEdge, MatrixNode, MatrixProposal } from "@/lib/bff/matrix-types";

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

export async function cpCreateMatrixNode(
  tenantId: string,
  engagementId: string,
  node: { node_type: string; title: string; status: string | null },
): Promise<MatrixNode> {
  const r = await fetch(matrixUrl(tenantId, engagementId, "nodes"), {
    method: "POST",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(node),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp matrix node create ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as MatrixNode;
}

export async function cpCreateMatrixEdge(
  tenantId: string,
  engagementId: string,
  edge: { edge_type: string; from_node_id: string; to_node_id: string },
): Promise<MatrixEdge> {
  const r = await fetch(matrixUrl(tenantId, engagementId, "edges"), {
    method: "POST",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(edge),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp matrix edge create ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as MatrixEdge;
}

function proposalsUrl(tenantId: string, engagementId: string, status?: string | null): string {
  const base =
    `${cpBase()}/internal/v1/engagements/${encodeURIComponent(engagementId)}/proposals` +
    `?tenant_id=${encodeURIComponent(tenantId)}`;
  return status ? `${base}&status=${encodeURIComponent(status)}` : base;
}

export async function cpListMatrixProposals(
  tenantId: string,
  engagementId: string,
  status: string | null = "pending",
): Promise<MatrixProposal[]> {
  const r = await fetch(proposalsUrl(tenantId, engagementId, status), {
    method: "GET",
    headers: cpHeaders(),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp matrix proposals list ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as MatrixProposal[];
}

async function cpDecideMatrixProposal(
  tenantId: string,
  engagementId: string,
  proposalId: string,
  decision: "accept" | "reject",
  body: { actor_id: string | null },
): Promise<MatrixProposal> {
  const url =
    `${cpBase()}/internal/v1/engagements/${encodeURIComponent(engagementId)}` +
    `/proposals/${encodeURIComponent(proposalId)}/${decision}` +
    `?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, {
    method: "POST",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp matrix proposal ${decision} ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as MatrixProposal;
}

export function cpAcceptMatrixProposal(
  tenantId: string,
  engagementId: string,
  proposalId: string,
  body: { actor_id: string | null },
): Promise<MatrixProposal> {
  return cpDecideMatrixProposal(tenantId, engagementId, proposalId, "accept", body);
}

export function cpRejectMatrixProposal(
  tenantId: string,
  engagementId: string,
  proposalId: string,
  body: { actor_id: string | null },
): Promise<MatrixProposal> {
  return cpDecideMatrixProposal(tenantId, engagementId, proposalId, "reject", body);
}

/**
 * Run the Phase 6.2c Cartographer extractor on one canonical event. Returns
 * the proposals it produced (or the existing ones, since the endpoint is
 * idempotent by event id unless `force=true`).
 */
export async function cpExtractMatrixProposals(
  tenantId: string,
  engagementId: string,
  eventId: string,
  opts: { force?: boolean } = {},
): Promise<MatrixProposal[]> {
  const params = new URLSearchParams({ tenant_id: tenantId, event_id: eventId });
  if (opts.force) {
    params.set("force", "true");
  }
  const url =
    `${cpBase()}/internal/v1/engagements/${encodeURIComponent(engagementId)}/extract?` +
    params.toString();
  const r = await fetch(url, {
    method: "POST",
    headers: cpHeaders(),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp matrix extract ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as MatrixProposal[];
}
