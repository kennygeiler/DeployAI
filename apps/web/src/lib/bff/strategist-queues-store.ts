/**
 * Epic 9 — in-process strategist queue fixtures for `next dev` / demo BFF routes.
 * Replaced by control-plane tables + internal APIs when those stories harden.
 *
 * **Deploy / FDE note:** state is per Node process only — horizontal scaling or rolling restarts
 * drop or split queue data unless you pin to one replica or move persistence to CP/DB.
 */

export type ActionQueueStatus =
  | "open"
  | "claimed"
  | "in_progress"
  | "resolved"
  | "deferred"
  | "rejected_with_reason";

export type ActionQueueItem = {
  id: string;
  priority: string;
  phase: string;
  description: string;
  status: ActionQueueStatus;
  claimed_by: string | null;
  updated_at: string;
  source?: string;
  evidence_node_ids?: string[];
  resolution_reason?: string | null;
  /** Optional linkage for resolved / rejected resolutions (FR56–58). */
  evidence_event_ids?: string[] | null;
};

export type ValidationQueueRow = {
  id: string;
  proposed_fact: string;
  confidence: string;
  state: "unresolved" | "in-review" | "resolved" | "escalated";
};

export type SolidificationQueueRow = {
  id: string;
  proposed_fact: string;
  confidence: string;
  state: "unresolved" | "in-review" | "resolved" | "escalated";
};

export type QueueAuditEvent = {
  at: string;
  tenantId: string;
  kind: string;
  payload: Record<string, unknown>;
};

type TenantKey = string;

const actionQueues = new Map<TenantKey, ActionQueueItem[]>();
const validationQueues = new Map<TenantKey, ValidationQueueRow[]>();
const solidQueues = new Map<TenantKey, SolidificationQueueRow[]>();
const inMeetingAudit: { tenantId: string; at: string; type: string; itemId?: string }[] = [];
const actionQueueAudits: QueueAuditEvent[] = [];
const validationAudits: QueueAuditEvent[] = [];
const solidificationAudits: QueueAuditEvent[] = [];

function tenantKey(tenantId: string | null | undefined): TenantKey {
  return tenantId?.trim() || "00000000-0000-4000-8000-000000000001";
}

function pushAudit(
  buf: QueueAuditEvent[],
  tenantId: string | null,
  kind: string,
  payload: Record<string, unknown>,
): void {
  buf.push({
    at: new Date().toISOString(),
    tenantId: tenantKey(tenantId),
    kind,
    payload,
  });
}

export function pushActionQueueAudit(
  tenantId: string | null,
  kind: string,
  payload: Record<string, unknown>,
): void {
  pushAudit(actionQueueAudits, tenantId, kind, payload);
}

export function snapshotActionQueueAudit(): QueueAuditEvent[] {
  return [...actionQueueAudits];
}

export function pushValidationAudit(
  tenantId: string | null,
  kind: string,
  payload: Record<string, unknown>,
): void {
  pushAudit(validationAudits, tenantId, kind, payload);
}

export function snapshotValidationAudit(): QueueAuditEvent[] {
  return [...validationAudits];
}

export function pushSolidificationAudit(
  tenantId: string | null,
  kind: string,
  payload: Record<string, unknown>,
): void {
  pushAudit(solidificationAudits, tenantId, kind, payload);
}

export function snapshotSolidificationAudit(): QueueAuditEvent[] {
  return [...solidificationAudits];
}

const VALIDATION_SEED: ValidationQueueRow[] = Array.from({ length: 10 }, (_, i) => ({
  id: `vq-${i + 1}`,
  proposed_fact: `Validation candidate ${i + 1}: low-confidence extraction pending strategist review.`,
  confidence: `${(0.55 + i * 0.03).toFixed(2)}`,
  state: "unresolved" as const,
}));

const SOLID_SEED: SolidificationQueueRow[] = Array.from({ length: 20 }, (_, i) => ({
  id: `sq-${i + 1}`,
  proposed_fact: `Class B candidate ${i + 1}: weekly solidification review item (mock).`,
  confidence: "Class B",
  state: "unresolved" as const,
}));

export function seedStrategistQueuesIfEmpty(tenantId: string | null): void {
  const k = tenantKey(tenantId);
  if (!validationQueues.has(k)) {
    validationQueues.set(
      k,
      VALIDATION_SEED.map((r) => ({ ...r })),
    );
  }
  if (!solidQueues.has(k)) {
    solidQueues.set(
      k,
      SOLID_SEED.map((r) => ({ ...r })),
    );
  }
  if (!actionQueues.has(k)) {
    actionQueues.set(k, []);
  }
}

/** Active validation items only (resolved / escalated drop from the surface per Epic 9.6). */
export function listValidationQueue(tenantId: string | null): ValidationQueueRow[] {
  seedStrategistQueuesIfEmpty(tenantId);
  const all = validationQueues.get(tenantKey(tenantId)) ?? [];
  return all.filter((r) => r.state === "unresolved" || r.state === "in-review");
}

/** Active Class B review items (promoted / demoted drop; deferred stays in-review). */
export function listSolidificationQueue(tenantId: string | null): SolidificationQueueRow[] {
  seedStrategistQueuesIfEmpty(tenantId);
  const all = solidQueues.get(tenantKey(tenantId)) ?? [];
  return all.filter((r) => r.state === "unresolved" || r.state === "in-review");
}

export function listActionQueue(tenantId: string | null): ActionQueueItem[] {
  seedStrategistQueuesIfEmpty(tenantId);
  return [...(actionQueues.get(tenantKey(tenantId)) ?? [])];
}

export function appendActionQueueItems(tenantId: string | null, rows: ActionQueueItem[]): void {
  const k = tenantKey(tenantId);
  seedStrategistQueuesIfEmpty(tenantId);
  const cur = actionQueues.get(k) ?? [];
  actionQueues.set(k, [...cur, ...rows]);
}

export function mutateActionQueueItem(
  tenantId: string | null,
  id: string,
  patch: {
    status: ActionQueueStatus;
    claimed_by?: string | null;
    updated_at?: string;
    resolution_reason?: string | null;
    evidence_event_ids?: string[] | null;
  },
): ActionQueueItem | null {
  const k = tenantKey(tenantId);
  const cur = actionQueues.get(k);
  if (!cur) {
    return null;
  }
  const i = cur.findIndex((x) => x.id === id);
  if (i < 0) {
    return null;
  }
  const row = cur[i]!;
  const terminal = ["resolved", "deferred", "rejected_with_reason"].includes(patch.status);
  const next: ActionQueueItem = {
    id: row.id,
    priority: row.priority,
    phase: row.phase,
    description: row.description,
    status: patch.status,
    claimed_by: patch.claimed_by !== undefined ? patch.claimed_by : row.claimed_by,
    updated_at: patch.updated_at ?? new Date().toISOString(),
    source: row.source,
    evidence_node_ids: row.evidence_node_ids,
    resolution_reason: terminal ? (patch.resolution_reason ?? null) : null,
    evidence_event_ids: terminal ? (patch.evidence_event_ids ?? null) : null,
  };
  const copy = [...cur];
  copy[i] = next;
  actionQueues.set(k, copy);
  return next;
}

export function patchValidationRow(
  tenantId: string | null,
  id: string,
  state: ValidationQueueRow["state"],
): ValidationQueueRow | null {
  const k = tenantKey(tenantId);
  const cur = validationQueues.get(k);
  if (!cur) {
    return null;
  }
  const i = cur.findIndex((x) => x.id === id);
  if (i < 0) {
    return null;
  }
  const row = cur[i]!;
  const next: ValidationQueueRow = {
    id: row.id,
    proposed_fact: row.proposed_fact,
    confidence: row.confidence,
    state,
  };
  const copy = [...cur];
  copy[i] = next;
  validationQueues.set(k, copy);
  return next;
}

export function patchSolidificationRow(
  tenantId: string | null,
  id: string,
  state: SolidificationQueueRow["state"],
): SolidificationQueueRow | null {
  const k = tenantKey(tenantId);
  const cur = solidQueues.get(k);
  if (!cur) {
    return null;
  }
  const i = cur.findIndex((x) => x.id === id);
  if (i < 0) {
    return null;
  }
  const row = cur[i]!;
  const next: SolidificationQueueRow = {
    id: row.id,
    proposed_fact: row.proposed_fact,
    confidence: row.confidence,
    state,
  };
  const copy = [...cur];
  copy[i] = next;
  solidQueues.set(k, copy);
  return next;
}

export function pushInMeetingAudit(
  tenantId: string | null,
  row: { type: string; itemId?: string },
): void {
  inMeetingAudit.push({
    tenantId: tenantKey(tenantId),
    at: new Date().toISOString(),
    type: row.type,
    itemId: row.itemId,
  });
}

export function snapshotInMeetingAudit(): typeof inMeetingAudit {
  return inMeetingAudit;
}
