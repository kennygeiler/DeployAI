/**
 * Wave 2.5 U3/U6 — engagement summary DTO (BFF ↔ control-plane).
 *
 * Backs the Brief's fast first paint: a small payload with the header
 * fields, member identities, count chips, and the recent-change feed. The
 * heavy matrix payload stays on the detail aggregate and loads lazily.
 *
 * Mirrors CP `GET /internal/v1/engagements/{id}/summary`. If that endpoint
 * is not deployed yet the BFF returns 404 and the Brief degrades to the
 * full-payload path.
 */

export type EngagementSummaryEngagement = {
  id: string;
  name: string;
  customer_account: string | null;
  current_phase: string;
  status: string;
  updated_at: string;
};

export type EngagementSummaryMember = {
  user_id: string;
  display_name: string | null;
  email: string | null;
  role: string;
};

export type EngagementSummaryCounts = {
  stakeholders: number;
  decisions: number;
  risks_open: number;
  commitments: number;
  proposals_pending: number;
  escalations_open: number;
  disputes_open: number;
};

export type EngagementSummaryChange = {
  occurred_at: string;
  kind: string;
  title: string;
  actor_display_name: string | null;
};

export type EngagementSummary = {
  engagement: EngagementSummaryEngagement;
  members: EngagementSummaryMember[];
  counts: EngagementSummaryCounts;
  recent_changes: EngagementSummaryChange[];
};
