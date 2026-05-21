/**
 * Shared DTO shapes for strategist queues (BFF ↔ control-plane).
 * Queue state lives only in Postgres via CP internal APIs.
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
  evidence_event_ids?: string[] | null;
  engagement_id?: string | null;
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
