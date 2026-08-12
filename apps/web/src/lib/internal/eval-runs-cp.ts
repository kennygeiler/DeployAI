/**
 * Control-plane client for the Wave 4 (G8) eval-run history list. Wraps
 * ``GET /internal/v1/admin/eval-runs`` — platform-level ops data recorded
 * by the golden eval runner (``runner.py --persist-url``).
 *
 * Same thin Zod-validated transport shape as
 * ``agent-kenny-dashboard-cp.ts``: schema lives here, the BFF round-trips
 * it, page + components import the inferred type.
 */
import { z } from "zod";

import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

export const EVAL_RUNS_LIMIT_DEFAULT = 50;
export const EVAL_RUNS_LIMIT_MAX = 500;

export const EvalRunSchema = z.object({
  id: z.string(),
  run_at: z.string(),
  source: z.string(),
  runtime: z.string().nullable(),
  question_count: z.number().int().nonnegative(),
  pass_rate: z.number().min(0).max(1),
  idk_rate: z.number().min(0).max(1),
  hallucination_rate: z.number().min(0).max(1),
  cross_engagement_leak_count: z.number().int().nonnegative(),
  p50_ms: z.number().nullable(),
  p95_ms: z.number().nullable(),
});
export type EvalRun = z.infer<typeof EvalRunSchema>;

export const EvalRunListSchema = z.object({
  runs: z.array(EvalRunSchema),
});
export type EvalRunList = z.infer<typeof EvalRunListSchema>;

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

export async function cpListEvalRuns(opts: { limit?: number } = {}): Promise<EvalRun[]> {
  const qs = new URLSearchParams();
  if (opts.limit !== undefined) qs.set("limit", String(opts.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  const url = `${cpBase()}/internal/v1/admin/eval-runs${suffix}`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) throw new Error(`cp eval-runs list ${r.status}: ${await r.text()}`);
  const raw: unknown = await r.json();
  return EvalRunListSchema.parse(raw).runs;
}
