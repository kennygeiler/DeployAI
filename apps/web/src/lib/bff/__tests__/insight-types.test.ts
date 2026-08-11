import { describe, expect, it } from "vitest";

import {
  normalizeMatrixInsight,
  normalizeTemporalInsight,
  type TemporalInsight,
} from "@/lib/bff/insight-types";
import { groupByKind } from "@/lib/bff/insight-grouping";
import type { MatrixInsight } from "@/lib/bff/matrix-types";

const matrix: MatrixInsight = {
  id: "m1",
  tenant_id: "t1",
  engagement_id: "e1",
  agent: "oracle",
  insight_type: "stale_commitment",
  severity: "high",
  title: "Ship date slipping",
  body: "Confirm a new date.",
  citation_node_ids: [],
  citation_edge_ids: [],
  citation_event_ids: ["ev1"],
  dedup_key: "k",
  status: "open",
  created_at: "2026-08-01T00:00:00Z",
  decided_at: null,
  decided_by: null,
};

const temporal: TemporalInsight = {
  id: "t1",
  tenant_id: "t1",
  engagement_id: "e1",
  insight_kind: "engagement_silence",
  severity: "critical",
  title: "No activity in 21 days",
  narrative: "Trailing silence across channels.",
  window_start: "2026-07-01T00:00:00Z",
  window_end: "2026-08-01T00:00:00Z",
  evidence_event_ids: [],
  metrics: {},
  status: "open",
  acknowledged_by: null,
  acknowledged_at: null,
  snoozed_until: "2026-08-20T00:00:00Z",
  created_at: "2026-08-02T00:00:00Z",
};

describe("insight normalization (F2)", () => {
  it("maps a MatrixInsight onto the unified shape", () => {
    const u = normalizeMatrixInsight(matrix);
    expect(u).toEqual({
      id: "m1",
      model: "matrix",
      engagement_id: "e1",
      insight_type: "stale_commitment",
      severity: "high",
      title: "Ship date slipping",
      body: "Confirm a new date.",
      status: "open",
      created_at: "2026-08-01T00:00:00Z",
      snoozed_until: null,
    });
  });

  it("maps a TemporalInsight onto the unified shape (kind + narrative renamed)", () => {
    const u = normalizeTemporalInsight(temporal);
    expect(u.model).toBe("temporal");
    expect(u.insight_type).toBe("engagement_silence");
    expect(u.body).toBe("Trailing silence across channels.");
    expect(u.severity).toBe("critical");
    expect(u.snoozed_until).toBe("2026-08-20T00:00:00Z");
  });

  it("normalized rows from both models group together by kind", () => {
    const groups = groupByKind([
      normalizeMatrixInsight(matrix),
      normalizeTemporalInsight(temporal),
    ]);
    expect(groups).toHaveLength(2);
    // critical temporal row sorts first.
    expect(groups[0]?.kind).toBe("engagement_silence");
    expect(groups[0]?.severityMax).toBe("critical");
    expect(groups[1]?.kind).toBe("stale_commitment");
    expect(groups[1]?.severityMax).toBe("critical");
  });
});
