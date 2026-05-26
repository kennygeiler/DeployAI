/**
 * Control-plane pre-canned scenario client.
 *
 * Wraps `POST /internal/v1/admin/seed-scenarios/{bluestate,bluestate-xl,portfolio}`
 * used by the onboarding wizard's picker cards. The CP routes run the same
 * seed natively that `make seed-scenario-bluestate` produces from the host.
 */
import { z } from "zod";

import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

export const zScenarioSummary = z.object({
  tenant_id: z.string(),
  engagement_id: z.string(),
  stakeholder_nodes: z.number(),
  decision_nodes: z.number(),
  risks: z.number(),
  snapshot_count: z.number(),
  temporal_insight_count: z.number(),
});
export type ScenarioSummary = z.infer<typeof zScenarioSummary>;

export const zSeedBluestateOk = z.object({
  engagement_id: z.string(),
  summary: zScenarioSummary,
  took_seconds: z.number(),
  source: z.string(),
});
export type SeedBluestateOk = z.infer<typeof zSeedBluestateOk>;

export const zSeedBluestateConflict = z.object({
  detail: z.object({
    error: z.literal("already_seeded"),
    engagement_id: z.string(),
  }),
});
export type SeedBluestateConflict = z.infer<typeof zSeedBluestateConflict>;

export type SeedBluestateResult =
  | { status: "ok"; body: SeedBluestateOk }
  | { status: "conflict"; body: SeedBluestateConflict }
  | { status: "error"; code: number; message: string };

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

export async function cpSeedBluestateScenario(
  tenantId: string,
  body: { force: boolean },
): Promise<SeedBluestateResult> {
  const url =
    `${cpBase()}/internal/v1/admin/seed-scenarios/bluestate` +
    `?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, {
    method: "POST",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (r.status === 200) {
    const parsed = zSeedBluestateOk.parse(await r.json());
    return { status: "ok", body: parsed };
  }
  if (r.status === 409) {
    const parsed = zSeedBluestateConflict.parse(await r.json());
    return { status: "conflict", body: parsed };
  }
  const text = await r.text();
  return { status: "error", code: r.status, message: text };
}

// ─────────────────────────────────────────────────────────────
// BlueState-XL (5-year fixture)
// ─────────────────────────────────────────────────────────────

export const zXlScenarioSummary = z.object({
  tenant_id: z.string(),
  engagement_id: z.string(),
  stakeholder_node_count: z.number(),
  decision_node_count: z.number(),
  risk_count: z.number(),
  narrative_event_count: z.number(),
  ledger_event_count: z.number(),
  matrix_edge_count: z.number(),
  snapshot_count: z.number(),
});
export type XlScenarioSummary = z.infer<typeof zXlScenarioSummary>;

export const zSeedBluestateXlOk = z.object({
  engagement_id: z.string(),
  summary: zXlScenarioSummary,
  took_seconds: z.number(),
  source: z.string(),
});
export type SeedBluestateXlOk = z.infer<typeof zSeedBluestateXlOk>;

export const zSeedBluestateXlConflict = z.object({
  detail: z.object({
    error: z.literal("already_seeded"),
    engagement_id: z.string(),
  }),
});
export type SeedBluestateXlConflict = z.infer<typeof zSeedBluestateXlConflict>;

export type SeedBluestateXlResult =
  | { status: "ok"; body: SeedBluestateXlOk }
  | { status: "conflict"; body: SeedBluestateXlConflict }
  | { status: "error"; code: number; message: string };

export async function cpStartBluestateXlSeed(
  tenantId: string,
  body: { force: boolean },
): Promise<SeedBluestateXlResult> {
  const url =
    `${cpBase()}/internal/v1/admin/seed-scenarios/bluestate-xl` +
    `?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, {
    method: "POST",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (r.status === 200) {
    const parsed = zSeedBluestateXlOk.parse(await r.json());
    return { status: "ok", body: parsed };
  }
  if (r.status === 409) {
    const parsed = zSeedBluestateXlConflict.parse(await r.json());
    return { status: "conflict", body: parsed };
  }
  const text = await r.text();
  return { status: "error", code: r.status, message: text };
}

// ─────────────────────────────────────────────────────────────
// DeployAI Portfolio (5 sibling engagements, isolation stress)
// ─────────────────────────────────────────────────────────────

export const zPortfolioSummary = z.object({
  tenant_id: z.string(),
  engagement_count: z.number(),
  engagements: z.array(zScenarioSummary),
});
export type PortfolioSummary = z.infer<typeof zPortfolioSummary>;

export const zSeedPortfolioOk = z.object({
  summary: zPortfolioSummary,
  took_seconds: z.number(),
  source: z.string(),
});
export type SeedPortfolioOk = z.infer<typeof zSeedPortfolioOk>;

export const zSeedPortfolioConflict = z.object({
  detail: z.object({
    error: z.literal("already_seeded"),
    engagement_ids: z.array(z.string()),
  }),
});
export type SeedPortfolioConflict = z.infer<typeof zSeedPortfolioConflict>;

export type SeedPortfolioResult =
  | { status: "ok"; body: SeedPortfolioOk }
  | { status: "conflict"; body: SeedPortfolioConflict }
  | { status: "error"; code: number; message: string };

export async function cpStartPortfolioSeed(
  tenantId: string,
  body: { force: boolean },
): Promise<SeedPortfolioResult> {
  const url =
    `${cpBase()}/internal/v1/admin/seed-scenarios/portfolio` +
    `?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, {
    method: "POST",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (r.status === 200) {
    const parsed = zSeedPortfolioOk.parse(await r.json());
    return { status: "ok", body: parsed };
  }
  if (r.status === 409) {
    const parsed = zSeedPortfolioConflict.parse(await r.json());
    return { status: "conflict", body: parsed };
  }
  const text = await r.text();
  return { status: "error", code: r.status, message: text };
}
