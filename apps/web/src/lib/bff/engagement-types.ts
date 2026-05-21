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
