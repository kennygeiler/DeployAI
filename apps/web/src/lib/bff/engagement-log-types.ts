/**
 * Shared DTO shape for engagement log entries (BFF ↔ control-plane).
 * Mirrors the control-plane `EngagementLogEntryRead` model.
 */

export type EngagementLogEntryKind = "meeting" | "decision" | "risk" | "next_action";

export type EngagementLogEntry = {
  id: string;
  engagement_id: string;
  entry_kind: string;
  body: string;
  author: string | null;
  /** Team role of the author at write time; null for pre-Phase-4.3 entries. */
  author_role: string | null;
  created_at: string;
};
