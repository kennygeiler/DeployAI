/**
 * Epic 9 — in-process strategist queue fixtures for `next dev` / demo BFF routes.
 * Replaced by control-plane tables + internal APIs when those stories harden.
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

type TenantKey = string;

const actionQueues = new Map<TenantKey, ActionQueueItem[]>();
const validationQueues = new Map<TenantKey, ValidationQueueRow[]>();
const solidQueues = new Map<TenantKey, SolidificationQueueRow[]>();
const inMeetingAudit: { tenantId: string; at: string; type: string; itemId?: string }[] = [];

function tenantKey(tenantId: string | null | undefined): TenantKey {
  return tenantId?.trim() || "00000000-0000-4000-8000-000000000001";
}

export function seedStrategistQueuesIfEmpty(tenantId: string | null): void {
  const k = tenantKey(tenantId);
  if (!validationQueues.has(k)) {
    validationQueues.set(k, [
      {
        id: "vq-1",
        proposed_fact: "Vendor A is sole-source for widget calibration (0.62 confidence).",
        confidence: "0.62",
        state: "unresolved",
      },
      {
        id: "vq-2",
        proposed_fact: "Phase gate P4 can proceed without additional environmental review.",
        confidence: "0.71",
        state: "unresolved",
      },
    ]);
  }
  if (!solidQueues.has(k)) {
    solidQueues.set(k, [
      {
        id: "sq-1",
        proposed_fact: "Class B — recurring spend pattern on cloud egress (medium confidence).",
        confidence: "Class B",
        state: "unresolved",
      },
    ]);
  }
  if (!actionQueues.has(k)) {
    actionQueues.set(k, []);
  }
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
  patch: { status: ActionQueueStatus; claimed_by?: string | null; updated_at?: string },
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
  };
  const copy = [...cur];
  copy[i] = next;
  actionQueues.set(k, copy);
  return next;
}

export function listValidationQueue(tenantId: string | null): ValidationQueueRow[] {
  seedStrategistQueuesIfEmpty(tenantId);
  return [...(validationQueues.get(tenantKey(tenantId)) ?? [])];
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

export function listSolidificationQueue(tenantId: string | null): SolidificationQueueRow[] {
  seedStrategistQueuesIfEmpty(tenantId);
  return [...(solidQueues.get(tenantKey(tenantId)) ?? [])];
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
