/**
 * Epic 9.3 — maps UI actions to audit event types (FR37: no silent mislearning).
 * Dismiss is audit-only; Correct records an explicit correction signal before Override flow.
 */
export type InMeetingItemAction = "correct" | "dismiss";

export function auditTypeForInMeetingAction(
  action: InMeetingItemAction,
): "alert.corrected" | "alert.dismissed" {
  return action === "correct" ? "alert.corrected" : "alert.dismissed";
}

/** True when the action must not update Oracle learning (dismiss only). */
export function isNonLearningInMeetingAction(action: InMeetingItemAction): boolean {
  return action === "dismiss";
}
