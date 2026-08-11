/**
 * Control-plane Review Inbox client (pilot-refresh E1/E2/E3).
 *
 * Wraps `/internal/v1/review-items` — list / counts / resolve / dismiss /
 * citation-dispute filing — so BFF routes and tests call typed helpers,
 * not raw URLs. Mirrors `insights-cp.ts`.
 */
import type { ReviewItem, ReviewItemCounts } from "@/lib/bff/review-types";

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

export type ReviewItemListFilters = {
  engagementId?: string | null;
  kind?: string | null;
  status?: string | null;
};

export async function cpListReviewItems(
  tenantId: string,
  filters: ReviewItemListFilters = {},
): Promise<ReviewItem[]> {
  const params = new URLSearchParams({ tenant_id: tenantId });
  if (filters.engagementId) params.set("engagement_id", filters.engagementId);
  if (filters.kind) params.set("kind", filters.kind);
  if (filters.status) params.set("status", filters.status);
  const r = await fetch(`${cpBase()}/internal/v1/review-items?${params.toString()}`, {
    method: "GET",
    headers: cpHeaders(),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp review items list ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as ReviewItem[];
}

export async function cpReviewItemCounts(tenantId: string): Promise<ReviewItemCounts> {
  const r = await fetch(
    `${cpBase()}/internal/v1/review-items/counts?tenant_id=${encodeURIComponent(tenantId)}`,
    { method: "GET", headers: cpHeaders(), cache: "no-store" },
  );
  if (!r.ok) {
    throw new Error(`cp review item counts ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as ReviewItemCounts;
}

export type ReviewItemResolveBody = {
  resolved_by: string | null;
  resolution_note?: string | null;
  answer_text?: string | null;
  answer_citations?: string[];
};

export async function cpResolveReviewItem(
  tenantId: string,
  itemId: string,
  body: ReviewItemResolveBody,
): Promise<ReviewItem> {
  return cpDecideReviewItem(tenantId, itemId, "resolve", body);
}

export type ReviewItemDismissBody = {
  resolved_by: string | null;
  resolution_note?: string | null;
};

export async function cpDismissReviewItem(
  tenantId: string,
  itemId: string,
  body: ReviewItemDismissBody,
): Promise<ReviewItem> {
  return cpDecideReviewItem(tenantId, itemId, "dismiss", body);
}

async function cpDecideReviewItem(
  tenantId: string,
  itemId: string,
  decision: "resolve" | "dismiss",
  body: Record<string, unknown>,
): Promise<ReviewItem> {
  const url =
    `${cpBase()}/internal/v1/review-items/${encodeURIComponent(itemId)}/${decision}` +
    `?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, {
    method: "POST",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp review item ${decision} ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as ReviewItem;
}

export type CitationDisputeCreateBody = {
  engagement_id?: string | null;
  turn_id?: string | null;
  citation_id: string;
  reason: string;
  created_by: string | null;
};

export async function cpFileCitationDispute(
  tenantId: string,
  body: CitationDisputeCreateBody,
): Promise<ReviewItem> {
  const url =
    `${cpBase()}/internal/v1/review-items/citation-disputes` +
    `?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, {
    method: "POST",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp citation dispute ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as ReviewItem;
}
