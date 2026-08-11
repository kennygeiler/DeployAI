/**
 * Wave 2.5 U3 — control-plane engagement summary fetch.
 *
 * Thin internal-API client for `GET /internal/v1/engagements/{id}/summary`,
 * validated with Zod so a CP shape drift fails loudly at the BFF boundary
 * instead of leaking a malformed payload into the Brief.
 */
import { z } from "zod";

import type { EngagementSummary } from "@/lib/bff/summary-types";
import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

const zSummaryEngagement = z.object({
  id: z.string(),
  name: z.string(),
  customer_account: z.string().nullable(),
  current_phase: z.string(),
  status: z.string(),
  updated_at: z.string(),
});

const zSummaryMember = z.object({
  user_id: z.string(),
  display_name: z.string().nullable(),
  email: z.string().nullable(),
  role: z.string(),
});

const zSummaryCounts = z.object({
  stakeholders: z.number().int().nonnegative(),
  decisions: z.number().int().nonnegative(),
  risks_open: z.number().int().nonnegative(),
  commitments: z.number().int().nonnegative(),
  proposals_pending: z.number().int().nonnegative(),
  escalations_open: z.number().int().nonnegative(),
  disputes_open: z.number().int().nonnegative(),
});

const zSummaryChange = z.object({
  occurred_at: z.string(),
  kind: z.string(),
  title: z.string(),
  actor_display_name: z.string().nullable(),
});

export const zEngagementSummary = z.object({
  engagement: zSummaryEngagement,
  members: z.array(zSummaryMember),
  counts: zSummaryCounts,
  recent_changes: z.array(zSummaryChange),
});

/** Thrown when the CP does not expose the summary endpoint (yet). */
export class SummaryEndpointUnavailableError extends Error {
  constructor() {
    super("cp engagement summary endpoint unavailable (404)");
    this.name = "SummaryEndpointUnavailableError";
  }
}

export async function cpGetEngagementSummary(
  tenantId: string,
  engagementId: string,
): Promise<EngagementSummary> {
  const base = getControlPlaneBaseUrl()?.replace(/\/$/, "");
  if (!base) {
    throw new Error("DEPLOYAI_CONTROL_PLANE_URL not set");
  }
  const key = getControlPlaneInternalKey();
  if (!key) {
    throw new Error("DEPLOYAI_INTERNAL_API_KEY not set");
  }
  const url =
    `${base}/internal/v1/engagements/${encodeURIComponent(engagementId)}/summary` +
    `?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, {
    method: "GET",
    headers: { "X-DeployAI-Internal-Key": key },
    cache: "no-store",
  });
  if (r.status === 404) {
    throw new SummaryEndpointUnavailableError();
  }
  if (!r.ok) {
    throw new Error(`cp engagement summary ${r.status}: ${await r.text()}`);
  }
  return zEngagementSummary.parse(await r.json());
}
