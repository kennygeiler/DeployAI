/**
 * Wave 5 GA2 — control-plane gap-asks fetch ("Kenny asks").
 *
 * Thin internal-API client for the CP gap-ask endpoints, validated with Zod
 * so a CP shape drift fails loudly at the BFF boundary instead of leaking a
 * malformed payload into the Brief.
 */
import { z } from "zod";

import type { GapAsk, GapAskDismissal } from "@/lib/bff/gap-ask-types";
import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

const zGapAsk = z.object({
  id: z.string(),
  rule: z.string(),
  severity: z.enum(["high", "medium", "low"]),
  target_node_id: z.string().nullable(),
  title: z.string(),
  why: z.string(),
  remedy_kind: z.enum(["capture", "forward", "answer"]),
});

const zGapAsksResponse = z.object({ asks: z.array(zGapAsk) });

const zGapAskDismissal = z.object({
  ask_id: z.string(),
  dismissed_at: z.string(),
  snooze_until: z.string().nullable(),
});

/** Thrown when the CP does not expose the gap-asks endpoint (yet). */
export class GapAsksEndpointUnavailableError extends Error {
  constructor() {
    super("cp gap-asks endpoint unavailable (404)");
    this.name = "GapAsksEndpointUnavailableError";
  }
}

function cpBase(): { base: string; key: string } {
  const base = getControlPlaneBaseUrl()?.replace(/\/$/, "");
  if (!base) {
    throw new Error("DEPLOYAI_CONTROL_PLANE_URL not set");
  }
  const key = getControlPlaneInternalKey();
  if (!key) {
    throw new Error("DEPLOYAI_INTERNAL_API_KEY not set");
  }
  return { base, key };
}

export async function cpGetGapAsks(tenantId: string, engagementId: string): Promise<GapAsk[]> {
  const { base, key } = cpBase();
  const url =
    `${base}/internal/v1/engagements/${encodeURIComponent(engagementId)}/gap-asks` +
    `?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, {
    method: "GET",
    headers: { "X-DeployAI-Internal-Key": key },
    cache: "no-store",
  });
  if (r.status === 404) {
    throw new GapAsksEndpointUnavailableError();
  }
  if (!r.ok) {
    throw new Error(`cp gap-asks ${r.status}: ${await r.text()}`);
  }
  return zGapAsksResponse.parse(await r.json()).asks;
}

async function cpPostGapAskAction(
  tenantId: string,
  engagementId: string,
  askId: string,
  action: "dismiss" | "snooze",
  body: Record<string, unknown>,
): Promise<GapAskDismissal> {
  const { base, key } = cpBase();
  const url =
    `${base}/internal/v1/engagements/${encodeURIComponent(engagementId)}` +
    `/gap-asks/${encodeURIComponent(askId)}/${action}` +
    `?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, {
    method: "POST",
    headers: { "X-DeployAI-Internal-Key": key, "content-type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (r.status === 404) {
    throw new GapAsksEndpointUnavailableError();
  }
  if (!r.ok) {
    throw new Error(`cp gap-ask ${action} ${r.status}: ${await r.text()}`);
  }
  return zGapAskDismissal.parse(await r.json());
}

export async function cpDismissGapAsk(
  tenantId: string,
  engagementId: string,
  askId: string,
  opts: { dismissedBy?: string | null } = {},
): Promise<GapAskDismissal> {
  return cpPostGapAskAction(tenantId, engagementId, askId, "dismiss", {
    dismissed_by: opts.dismissedBy ?? null,
  });
}

export async function cpSnoozeGapAsk(
  tenantId: string,
  engagementId: string,
  askId: string,
  opts: { days: number; dismissedBy?: string | null },
): Promise<GapAskDismissal> {
  return cpPostGapAskAction(tenantId, engagementId, askId, "snooze", {
    days: opts.days,
    dismissed_by: opts.dismissedBy ?? null,
  });
}
