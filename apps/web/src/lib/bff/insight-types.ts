/**
 * Pilot-refresh F2 — unified insight shape.
 *
 * The app has two insight models: `MatrixInsight` (Oracle synthesis rows in
 * `matrix_insights`; dismiss/resolve) and temporal insights (analyzer rows in
 * `temporal_insights`; snooze/follow-up/acknowledge). The BFF read path
 * normalizes both into `UnifiedInsight` so `EngagementInsights` renders one
 * list and dispatches each action to the correct backend by `model`.
 *
 * `insight_type` keeps its MatrixInsight field name so the grouping helpers
 * (`insight-grouping.ts`) work structurally over both the raw and the
 * unified shapes.
 */
import type { MatrixInsight } from "@/lib/bff/matrix-types";

export type UnifiedInsightSeverity = "info" | "low" | "medium" | "high" | "critical";

export type InsightModel = "matrix" | "temporal";

export type UnifiedInsight = {
  id: string;
  model: InsightModel;
  engagement_id: string | null;
  insight_type: string;
  severity: UnifiedInsightSeverity;
  title: string;
  body: string;
  status: string;
  created_at: string;
  snoozed_until: string | null;
};

/** Temporal insight DTO — mirrors CP `TemporalInsightRead`. */
export type TemporalInsight = {
  id: string;
  tenant_id: string;
  engagement_id: string | null;
  insight_kind: string;
  severity: "info" | "low" | "medium" | "high" | "critical";
  title: string;
  narrative: string;
  window_start: string;
  window_end: string;
  evidence_event_ids: string[];
  metrics: Record<string, unknown>;
  status: string;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  snoozed_until: string | null;
  created_at: string;
};

export function normalizeMatrixInsight(insight: MatrixInsight): UnifiedInsight {
  return {
    id: insight.id,
    model: "matrix",
    engagement_id: insight.engagement_id,
    insight_type: insight.insight_type,
    severity: insight.severity,
    title: insight.title,
    body: insight.body,
    status: insight.status,
    created_at: insight.created_at,
    snoozed_until: null,
  };
}

export function normalizeTemporalInsight(insight: TemporalInsight): UnifiedInsight {
  return {
    id: insight.id,
    model: "temporal",
    engagement_id: insight.engagement_id,
    insight_type: insight.insight_kind,
    severity: insight.severity,
    title: insight.title,
    body: insight.narrative,
    status: insight.status,
    created_at: insight.created_at,
    snoozed_until: insight.snoozed_until,
  };
}
