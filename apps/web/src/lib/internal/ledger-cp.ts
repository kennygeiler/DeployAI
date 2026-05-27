import { z } from "zod";

import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

// Mirrors the CP source_kind enum (docs/design/timeline-ledger.md §3.1 + §4.3).
// Sibling F1.d list route declares the same set locally; we redeclare here so
// the chain BFF route can validate response nodes without cross-route coupling.
export const ALLOWED_SOURCE_KINDS: ReadonlySet<string> = new Set([
  "email_ingest",
  "meeting_webhook",
  "manual_capture",
  "llm_proposal_created",
  "proposal_accepted",
  "proposal_rejected",
  "matrix_node_created",
  "matrix_node_updated",
  "matrix_node_deleted",
  "matrix_edge_created",
  "matrix_edge_deleted",
  "insight_opened",
  "insight_closed",
  "recommendation_emitted",
  "recommendation_actioned",
  "engagement_phase_change",
  "member_added",
  "member_removed",
  "settings_change",
  "audit_other",
  "user_provisioned",
  "audit_decision",
  "insight_snoozed",
  "followup_task_created",
  "oracle_chat_turn",
  // v2 Phase 5 Wave 3I — outbound MCP activity (Wave 2D emits these from
  // ``mcp_client.py``). The timeline filter chip "External (MCP)" toggles
  // the four call-status kinds; the config-change + kill-switch +
  // oauth-rotation kinds get rendered with a distinct tag.
  "mcp_outbound_call",
  "mcp_outbound_blocked",
  "mcp_outbound_rate_limited",
  "mcp_outbound_denied",
  "mcp_outbound_killswitch_changed",
  "mcp_config_created",
  "mcp_config_updated",
  "mcp_config_deleted",
  "mcp_oauth_token_rotated",
]);

/**
 * The subset of source_kinds that represent an actual outbound call
 * attempt to an external MCP server (success or failure). The "External
 * (MCP)" timeline filter chip and the admin audit panel both narrow to
 * this set. Distinct from ``MCP_CONFIG_SOURCE_KINDS`` (tenant-admin
 * configuration changes) and ``MCP_KILLSWITCH_SOURCE_KIND`` (incident
 * response toggle) so each can be rendered with its own tag.
 */
export const MCP_OUTBOUND_CALL_SOURCE_KINDS: readonly string[] = [
  "mcp_outbound_call",
  "mcp_outbound_blocked",
  "mcp_outbound_rate_limited",
  "mcp_outbound_denied",
] as const;

export const MCP_CONFIG_SOURCE_KINDS: readonly string[] = [
  "mcp_config_created",
  "mcp_config_updated",
  "mcp_config_deleted",
  "mcp_oauth_token_rotated",
] as const;

export const MCP_KILLSWITCH_SOURCE_KIND = "mcp_outbound_killswitch_changed";

/** Union of every MCP-related source kind (call + config + killswitch). */
export const MCP_ALL_SOURCE_KINDS: readonly string[] = [
  ...MCP_OUTBOUND_CALL_SOURCE_KINDS,
  ...MCP_CONFIG_SOURCE_KINDS,
  MCP_KILLSWITCH_SOURCE_KIND,
] as const;

export function isMcpOutboundCallKind(kind: string): boolean {
  return (MCP_OUTBOUND_CALL_SOURCE_KINDS as readonly string[]).includes(kind);
}

export function isMcpConfigKind(kind: string): boolean {
  return (MCP_CONFIG_SOURCE_KINDS as readonly string[]).includes(kind);
}

export function isMcpKillswitchKind(kind: string): boolean {
  return kind === MCP_KILLSWITCH_SOURCE_KIND;
}

export const zLedgerEventAffect = z.object({
  entity_kind: z.string(),
  entity_id: z.string(),
});

// Defense-in-depth: CP `emit_ledger_event` strips known secret keys
// before insert, but we also strip on the BFF→client hop so a CP-side
// regression can't leak credentials into the timeline UI.
const SECRET_DETAIL_KEYS = new Set([
  "api_key",
  "signing_secret",
  "webhook_url",
  "secondary_api_key",
  "secret",
  "token",
  "password",
]);

function stripSecretKeys(obj: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(obj)) {
    if (SECRET_DETAIL_KEYS.has(k.toLowerCase())) continue;
    out[k] = v;
  }
  return out;
}

export const zLedgerEvent = z.object({
  id: z.string(),
  engagement_id: z.string().nullable(),
  occurred_at: z.string(),
  recorded_at: z.string(),
  actor_kind: z.string(),
  actor_id: z.string().nullable(),
  source_kind: z.string(),
  source_ref: z.string().nullable(),
  summary: z.string(),
  detail: z.record(z.string(), z.unknown()).transform(stripSecretKeys),
  caused_by_ids: z.array(z.string()).default([]),
  affects: z.array(zLedgerEventAffect).default([]),
});

export type LedgerEvent = z.infer<typeof zLedgerEvent>;

export const zLedgerEventList = z.object({
  events: z.array(zLedgerEvent),
  next_cursor: z.string().nullable().default(null),
});

export type LedgerEventList = z.infer<typeof zLedgerEventList>;

export type LedgerListOpts = {
  from?: string;
  to?: string;
  source_kind?: string[];
  actor_id?: string;
  affects_entity_kind?: string;
  affects_entity_id?: string;
  cursor?: string;
  limit?: number;
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

export async function cpListLedger(
  tenantId: string,
  engagementId: string,
  opts: LedgerListOpts = {},
): Promise<LedgerEventList> {
  const qs = new URLSearchParams({ tenant_id: tenantId });
  if (opts.from) qs.set("from", opts.from);
  if (opts.to) qs.set("to", opts.to);
  if (opts.source_kind && opts.source_kind.length > 0) {
    qs.set("source_kind", opts.source_kind.join(","));
  }
  if (opts.actor_id) qs.set("actor_id", opts.actor_id);
  if (opts.affects_entity_kind) qs.set("affects_entity_kind", opts.affects_entity_kind);
  if (opts.affects_entity_id) qs.set("affects_entity_id", opts.affects_entity_id);
  if (opts.cursor) qs.set("cursor", opts.cursor);
  if (opts.limit !== undefined) qs.set("limit", String(opts.limit));
  const url =
    `${cpBase()}/internal/v1/engagements/${encodeURIComponent(engagementId)}/ledger` +
    `?${qs.toString()}`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp ledger list ${r.status}: ${await r.text()}`);
  }
  const raw: unknown = await r.json();
  return zLedgerEventList.parse(raw);
}

export async function cpGetLedgerEvent(
  tenantId: string,
  engagementId: string,
  eventId: string,
): Promise<LedgerEvent> {
  const qs = new URLSearchParams({ tenant_id: tenantId });
  const url =
    `${cpBase()}/internal/v1/engagements/${encodeURIComponent(engagementId)}/ledger/` +
    `${encodeURIComponent(eventId)}?${qs.toString()}`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp ledger get ${r.status}: ${await r.text()}`);
  }
  const raw: unknown = await r.json();
  return zLedgerEvent.parse(raw);
}

// CP returns snake_case (FastAPI Pydantic defaults). We map to camelCase on the
// BFF boundary so the web consumer stays JS-idiomatic and so an accidental CP
// rename surfaces as a schema error here instead of a silent `undefined` in the
// tree component.
const zChainNodeRaw = z.object({
  id: z.string(),
  occurred_at: z.string(),
  source_kind: z.string(),
  summary: z.string(),
  actor_kind: z.string(),
  depth: z.number().int().nonnegative(),
  truncated: z.boolean(),
});

const zChainEdgeRaw = z.object({
  from_event_id: z.string(),
  to_event_id: z.string(),
});

const zChainResponseRaw = z.object({
  root_event_id: z.string(),
  nodes: z.array(zChainNodeRaw),
  edges: z.array(zChainEdgeRaw),
  truncated_at_depth: z.number().int().nonnegative().nullable(),
  truncated_node_count: z.number().int().nonnegative().nullable(),
});

export const zChainNode = zChainNodeRaw.transform((n) => ({
  id: n.id,
  occurredAt: n.occurred_at,
  sourceKind: n.source_kind,
  summary: n.summary,
  actorKind: n.actor_kind,
  depth: n.depth,
  truncated: n.truncated,
}));

export type ChainNode = z.infer<typeof zChainNode>;

export const zChainEdge = zChainEdgeRaw.transform((e) => ({
  fromEventId: e.from_event_id,
  toEventId: e.to_event_id,
}));

export type ChainEdge = z.infer<typeof zChainEdge>;

export const zChainResponse = zChainResponseRaw.transform((r) => ({
  rootEventId: r.root_event_id,
  nodes: r.nodes.map((n) => ({
    id: n.id,
    occurredAt: n.occurred_at,
    sourceKind: n.source_kind,
    summary: n.summary,
    actorKind: n.actor_kind,
    depth: n.depth,
    truncated: n.truncated,
  })),
  edges: r.edges.map((e) => ({
    fromEventId: e.from_event_id,
    toEventId: e.to_event_id,
  })),
  truncatedAtDepth: r.truncated_at_depth,
  truncatedNodeCount: r.truncated_node_count,
}));

export type ChainResponse = z.infer<typeof zChainResponse>;

export type ChainOpts = {
  direction?: "backward" | "forward" | "both";
  max_depth?: number;
};

export async function cpFetchChain(
  tenantId: string,
  engagementId: string,
  eventId: string,
  opts: ChainOpts = {},
): Promise<ChainResponse> {
  const qs = new URLSearchParams({ tenant_id: tenantId });
  if (opts.direction) qs.set("direction", opts.direction);
  if (opts.max_depth !== undefined) qs.set("max_depth", String(opts.max_depth));
  const url =
    `${cpBase()}/internal/v1/engagements/${encodeURIComponent(engagementId)}/ledger/` +
    `${encodeURIComponent(eventId)}/chain?${qs.toString()}`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp ledger chain ${r.status}: ${await r.text()}`);
  }
  const raw: unknown = await r.json();
  return zChainResponse.parse(raw);
}
