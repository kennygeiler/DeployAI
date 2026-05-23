/**
 * Shared DTO shapes for Phase 6 ingestion (BFF ↔ control-plane).
 * Mirror the control-plane `IngestInteractionCreate` / `IngestedEventRead`.
 */

export type IngestSource = "manual_import" | "meeting_note" | "email" | "field_note";

export type IngestInteractionPayload = {
  source: IngestSource | string;
  occurred_at: string;
  content: Record<string, unknown>;
  source_ref?: string | null;
  dedup_key?: string | null;
};

export type IngestedEvent = {
  id: string;
  engagement_id: string | null;
  event_type: string;
  occurred_at: string;
  source_ref: string | null;
  ingestion_dedup_key: string | null;
  payload: Record<string, unknown>;
  created_at: string;
};
