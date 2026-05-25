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
]);

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

export const zChainNode = z.object({
  id: z.string(),
  occurredAt: z.string(),
  sourceKind: z.string(),
  summary: z.string(),
  actorKind: z.string(),
  depth: z.number().int().nonnegative(),
  truncated: z.boolean(),
});

export type ChainNode = z.infer<typeof zChainNode>;

export const zChainEdge = z.object({
  fromEventId: z.string(),
  toEventId: z.string(),
});

export type ChainEdge = z.infer<typeof zChainEdge>;

export const zChainResponse = z.object({
  rootEventId: z.string(),
  nodes: z.array(zChainNode),
  edges: z.array(zChainEdge),
  truncatedAtDepth: z.number().int().nonnegative().nullable(),
  truncatedNodeCount: z.number().int().nonnegative().nullable(),
});

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
