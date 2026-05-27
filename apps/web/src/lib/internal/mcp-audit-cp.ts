/**
 * Control-plane client for the tenant-wide outbound-MCP audit slice
 * (Wave 3I). Wraps the CP route
 * ``GET /internal/v1/tenants/{tenant_id}/mcp_audit`` which returns the
 * last N ledger rows with one of the MCP-related source_kinds.
 *
 * The detail blob is already redacted on the CP write path (Wave 2D's
 * ``_SECRET_KEY_NEEDLES`` backstop + per-source whitelist) — this client
 * surfaces it unchanged so the admin table can pluck out
 * ``connector_kind``, ``tool``, ``latency_ms``, etc. without a second
 * round-trip.
 */
import { z } from "zod";

import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

export const McpAuditRowSchema = z.object({
  id: z.string(),
  engagement_id: z.string().nullable(),
  occurred_at: z.string(),
  actor_kind: z.string(),
  actor_id: z.string().nullable(),
  source_kind: z.string(),
  source_ref: z.string().nullable(),
  summary: z.string(),
  detail: z.record(z.string(), z.unknown()),
});

export type McpAuditRow = z.infer<typeof McpAuditRowSchema>;

const McpAuditResponseSchema = z.object({
  rows: z.array(McpAuditRowSchema),
});

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

export async function cpListMcpAudit(
  tenantId: string,
  opts: { limit?: number } = {},
): Promise<McpAuditRow[]> {
  const qs = new URLSearchParams();
  if (opts.limit !== undefined) qs.set("limit", String(opts.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  const url = `${cpBase()}/internal/v1/tenants/${encodeURIComponent(tenantId)}/mcp_audit${suffix}`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) throw new Error(`cp mcp_audit list ${r.status}: ${await r.text()}`);
  const raw: unknown = await r.json();
  return McpAuditResponseSchema.parse(raw).rows;
}
