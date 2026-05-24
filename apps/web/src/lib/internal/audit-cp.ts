import { z } from "zod";

import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

export type AuditEvent = {
  id: string;
  tenant_id: string;
  actor_id: string;
  category: string;
  summary: string;
  detail: Record<string, unknown>;
  ref_id: string | null;
  created_at: string;
};

export type AuditListOpts = {
  limit?: number;
  before?: string;
  actor?: string;
  kind?: string;
};

export const zAuditEvent = z.object({
  id: z.string(),
  tenant_id: z.string(),
  actor_id: z.string(),
  category: z.string(),
  summary: z.string(),
  detail: z.record(z.string(), z.unknown()),
  ref_id: z.string().nullable(),
  created_at: z.string(),
});

const zAuditEventList = z.array(zAuditEvent);

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

export async function cpListAuditEvents(
  tenantId: string,
  opts: AuditListOpts = {},
): Promise<AuditEvent[]> {
  const qs = new URLSearchParams({ tenant_id: tenantId });
  if (opts.limit !== undefined) qs.set("limit", String(opts.limit));
  if (opts.before) qs.set("before", opts.before);
  if (opts.actor) qs.set("actor", opts.actor);
  if (opts.kind) qs.set("kind", opts.kind);
  const url = `${cpBase()}/internal/v1/audit-events?${qs.toString()}`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp audit-events list ${r.status}: ${await r.text()}`);
  }
  const raw: unknown = await r.json();
  return zAuditEventList.parse(raw);
}
