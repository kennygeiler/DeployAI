/**
 * Review Inbox DTOs (pilot-refresh E1). Mirror the control-plane
 * `ReviewItemRead` / `ReviewItemCounts` models in
 * `api/routes/review_inbox_internal.py`.
 *
 * `extraction_proposal` appears in the inbox UI but is NOT stored in
 * `review_items` — the inbox lists those via the existing proposals API
 * (engagement detail aggregate) and merges client-side.
 */

export const STORED_REVIEW_ITEM_KINDS = [
  "agent_escalation",
  "citation_dispute",
  "commitment_confirmation",
] as const;

export type StoredReviewItemKind = (typeof STORED_REVIEW_ITEM_KINDS)[number];

/** All four inbox surfaces, including the proposals-backed one. */
export type ReviewInboxKind = StoredReviewItemKind | "extraction_proposal";

export type ReviewItemStatus = "open" | "resolved" | "dismissed";

export type ReviewItem = {
  id: string;
  tenant_id: string;
  engagement_id: string | null;
  kind: StoredReviewItemKind;
  status: ReviewItemStatus;
  payload: Record<string, unknown>;
  created_by: string | null;
  resolved_by: string | null;
  resolution_note: string | null;
  created_at: string;
  resolved_at: string | null;
};

export type ReviewItemCounts = {
  open: number;
  agent_escalation: number;
  citation_dispute: number;
  commitment_confirmation: number;
};

export function isStoredReviewItemKind(value: string): value is StoredReviewItemKind {
  return (STORED_REVIEW_ITEM_KINDS as readonly string[]).includes(value);
}
