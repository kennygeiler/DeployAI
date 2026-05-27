/**
 * Control-plane client for the Phase 6 Wave C Agent Kenny telemetry
 * dashboard aggregate. Wraps the CP route
 * ``GET /internal/v1/tenants/{tenant_id}/agent_kenny_dashboard``.
 *
 * The CP route already does all aggregation server-side — this client is
 * a thin Zod-validated transport. Keeping the schema here (rather than
 * importing from a shared package) lets the BFF round-trip without a CP
 * shape leak; the page + client component import the inferred type.
 */
import { z } from "zod";

import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

export const WINDOW_DAYS_MIN = 1;
export const WINDOW_DAYS_MAX = 90;
export const WINDOW_DAYS_DEFAULT = 7;

export const ToolCallCountSchema = z.object({
  tool: z.string(),
  count: z.number().int().nonnegative(),
});
export type ToolCallCount = z.infer<typeof ToolCallCountSchema>;

export const LintFlagCountSchema = z.object({
  kind: z.string(),
  count: z.number().int().nonnegative(),
  most_recent: z.string().nullable(),
});
export type LintFlagCount = z.infer<typeof LintFlagCountSchema>;

export const TopCitedEventSchema = z.object({
  event_id: z.string(),
  summary: z.string(),
  citation_count: z.number().int().nonnegative(),
});
export type TopCitedEvent = z.infer<typeof TopCitedEventSchema>;

export const AgentKennyDashboardSchema = z.object({
  window_days: z.number().int().min(WINDOW_DAYS_MIN).max(WINDOW_DAYS_MAX),
  hallucination_rate: z.number().min(0).max(1),
  citations_total: z.number().int().nonnegative(),
  citations_unverified: z.number().int().nonnegative(),
  latency_p50_ms: z.number().int().nonnegative(),
  latency_p95_ms: z.number().int().nonnegative(),
  latency_p99_ms: z.number().int().nonnegative(),
  idk_rate: z.number().min(0).max(1),
  tool_calls: z.array(ToolCallCountSchema),
  lint_flag_counts: z.array(LintFlagCountSchema),
  top_cited_events: z.array(TopCitedEventSchema),
  adversarial_concerns_total: z.number().int().nonnegative(),
});
export type AgentKennyDashboard = z.infer<typeof AgentKennyDashboardSchema>;

function cpHeaders(): Record<string, string> {
  const key = getControlPlaneInternalKey();
  if (!key) throw new Error("DEPLOYAI_INTERNAL_API_KEY not set");
  return { "X-DeployAI-Internal-Key": key };
}

function cpBase(): string {
  const base = getControlPlaneBaseUrl()?.replace(/\/$/, "");
  if (!base) throw new Error("DEPLOYAI_CONTROL_PLANE_URL not set");
  return base;
}

export async function cpGetAgentKennyDashboard(
  tenantId: string,
  opts: { windowDays?: number } = {},
): Promise<AgentKennyDashboard> {
  const qs = new URLSearchParams();
  if (opts.windowDays !== undefined) qs.set("window_days", String(opts.windowDays));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  const url = `${cpBase()}/internal/v1/tenants/${encodeURIComponent(tenantId)}/agent_kenny_dashboard${suffix}`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) throw new Error(`cp agent_kenny_dashboard ${r.status}: ${await r.text()}`);
  const raw: unknown = await r.json();
  return AgentKennyDashboardSchema.parse(raw);
}
