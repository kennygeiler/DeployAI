/**
 * Control-plane engagement-recommendations API (internal key). Deterministic
 * next-action surface — no LLM call. Mirrors the read-only shape of the
 * CP route.
 */
import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

export type RecommendationRole = "fde" | "deployment_strategist" | "biz_dev";
export type RecommendationPriority = "high" | "medium" | "low";

export type Recommendation = {
  id: string;
  role: RecommendationRole;
  priority: RecommendationPriority;
  title: string;
  body: string;
  citation_node_ids: string[];
  citation_edge_ids: string[];
};

export type RecommendationsResponse = {
  recommendations: Recommendation[];
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

export async function cpListRecommendations(
  tenantId: string,
  engagementId: string,
): Promise<RecommendationsResponse> {
  const url =
    `${cpBase()}/internal/v1/engagements/${encodeURIComponent(engagementId)}/recommendations` +
    `?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp engagement recommendations ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as RecommendationsResponse;
}
