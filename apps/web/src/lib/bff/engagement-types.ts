/**
 * Shared DTO shape for engagements (BFF ↔ control-plane).
 * Mirrors the control-plane `EngagementRead` model.
 */

export type Engagement = {
  id: string;
  tenant_id: string;
  name: string;
  customer_account: string | null;
  current_phase: string;
  status: string;
  created_at: string;
  updated_at: string;
};

/**
 * A user's membership on an engagement, with their team role.
 * Mirrors the control-plane `EngagementMemberRead` model.
 */
export type EngagementMember = {
  id: string;
  engagement_id: string;
  user_id: string;
  role: string;
  created_at: string;
  /** Wave 2.5 U2 (additive) — human identity fields for member rendering. */
  display_name?: string | null;
  email?: string | null;
};

/**
 * Wave 2.5 U7 (additive) — needs-attention rollup on engagement list rows.
 * Older CP builds omit these fields; render paths must treat them as absent.
 */
export type EngagementNeedsAttention = {
  proposals_pending: number;
  escalations_open: number;
  days_since_last_event: number;
};

export type EngagementListRow = Engagement & {
  needs_attention?: EngagementNeedsAttention | null;
  attention_score?: number | null;
};
