/**
 * Control-plane matrix-insights API (internal key). Wraps the Phase 7.2
 * Oracle endpoints — list / refresh / dismiss / resolve — so BFF routes
 * (and tests) call typed helpers, not raw URLs. Mirrors `matrix-cp.ts`.
 */
import type { MatrixInsight } from "@/lib/bff/matrix-types";

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

function insightsUrl(
  tenantId: string,
  engagementId: string,
  status: "open" | "dismissed" | "resolved" | null,
): string {
  const base =
    `${cpBase()}/internal/v1/engagements/${encodeURIComponent(engagementId)}/insights` +
    `?tenant_id=${encodeURIComponent(tenantId)}`;
  return status ? `${base}&status=${encodeURIComponent(status)}` : base;
}

export async function cpListMatrixInsights(
  tenantId: string,
  engagementId: string,
  status: "open" | "dismissed" | "resolved" | null = "open",
): Promise<MatrixInsight[]> {
  const r = await fetch(insightsUrl(tenantId, engagementId, status), {
    method: "GET",
    headers: cpHeaders(),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp matrix insights list ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as MatrixInsight[];
}

export async function cpRefreshMatrixInsights(
  tenantId: string,
  engagementId: string,
): Promise<MatrixInsight[]> {
  const url =
    `${cpBase()}/internal/v1/engagements/${encodeURIComponent(engagementId)}/insights/refresh` +
    `?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, {
    method: "POST",
    headers: cpHeaders(),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp matrix insights refresh ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as MatrixInsight[];
}

async function cpDecideMatrixInsight(
  tenantId: string,
  engagementId: string,
  insightId: string,
  decision: "dismiss" | "resolve",
  body: { actor_id: string | null },
): Promise<MatrixInsight> {
  const url =
    `${cpBase()}/internal/v1/engagements/${encodeURIComponent(engagementId)}` +
    `/insights/${encodeURIComponent(insightId)}/${decision}` +
    `?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, {
    method: "POST",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp matrix insight ${decision} ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as MatrixInsight;
}

export function cpDismissMatrixInsight(
  tenantId: string,
  engagementId: string,
  insightId: string,
  body: { actor_id: string | null },
): Promise<MatrixInsight> {
  return cpDecideMatrixInsight(tenantId, engagementId, insightId, "dismiss", body);
}

export function cpResolveMatrixInsight(
  tenantId: string,
  engagementId: string,
  insightId: string,
  body: { actor_id: string | null },
): Promise<MatrixInsight> {
  return cpDecideMatrixInsight(tenantId, engagementId, insightId, "resolve", body);
}

// --- Phase 7.4 — tenant-scoped (Master Strategist) insights ----------------

function tenantInsightsUrl(
  tenantId: string,
  status: "open" | "dismissed" | "resolved" | null,
): string {
  const base = `${cpBase()}/internal/v1/tenants/${encodeURIComponent(tenantId)}/insights`;
  return status ? `${base}?status=${encodeURIComponent(status)}` : base;
}

export async function cpListTenantInsights(
  tenantId: string,
  status: "open" | "dismissed" | "resolved" | null = "open",
): Promise<MatrixInsight[]> {
  const r = await fetch(tenantInsightsUrl(tenantId, status), {
    method: "GET",
    headers: cpHeaders(),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp tenant insights list ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as MatrixInsight[];
}

export async function cpRefreshTenantInsights(tenantId: string): Promise<MatrixInsight[]> {
  const url = `${cpBase()}/internal/v1/tenants/${encodeURIComponent(tenantId)}/insights/refresh`;
  const r = await fetch(url, {
    method: "POST",
    headers: cpHeaders(),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp tenant insights refresh ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as MatrixInsight[];
}

async function cpDecideTenantInsight(
  tenantId: string,
  insightId: string,
  decision: "dismiss" | "resolve",
  body: { actor_id: string | null },
): Promise<MatrixInsight> {
  const url =
    `${cpBase()}/internal/v1/tenants/${encodeURIComponent(tenantId)}` +
    `/insights/${encodeURIComponent(insightId)}/${decision}`;
  const r = await fetch(url, {
    method: "POST",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp tenant insight ${decision} ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as MatrixInsight;
}

export function cpDismissTenantInsight(
  tenantId: string,
  insightId: string,
  body: { actor_id: string | null },
): Promise<MatrixInsight> {
  return cpDecideTenantInsight(tenantId, insightId, "dismiss", body);
}

export function cpResolveTenantInsight(
  tenantId: string,
  insightId: string,
  body: { actor_id: string | null },
): Promise<MatrixInsight> {
  return cpDecideTenantInsight(tenantId, insightId, "resolve", body);
}

// --- G4.b — temporal insight snooze + followup quick-actions ----------------

export type TemporalInsightSnoozeResponse = {
  insight_id: string;
  status: string;
  snoozed_until: string;
};

export type TemporalInsightFollowupResponse = {
  action_queue_item_id: string;
  insight_id: string;
};

export async function cpSnoozeTemporalInsight(
  tenantId: string,
  engagementId: string,
  insightId: string,
  body: { days: number },
): Promise<TemporalInsightSnoozeResponse> {
  const url =
    `${cpBase()}/internal/v1/engagements/${encodeURIComponent(engagementId)}` +
    `/insights/${encodeURIComponent(insightId)}/snooze` +
    `?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, {
    method: "POST",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp insight snooze ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as TemporalInsightSnoozeResponse;
}

export async function cpCreateInsightFollowup(
  tenantId: string,
  engagementId: string,
  insightId: string,
  body: { owner_user_id: string; due_date: string },
): Promise<TemporalInsightFollowupResponse> {
  const url =
    `${cpBase()}/internal/v1/engagements/${encodeURIComponent(engagementId)}` +
    `/insights/${encodeURIComponent(insightId)}/followup` +
    `?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, {
    method: "POST",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp insight followup ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as TemporalInsightFollowupResponse;
}
