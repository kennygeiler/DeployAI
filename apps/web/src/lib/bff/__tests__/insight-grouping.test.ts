import { describe, expect, it } from "vitest";

import {
  groupByKind,
  humanizeKind,
  isOpenByDefault,
  toGroupSeverity,
  type InsightGroup,
} from "@/lib/bff/insight-grouping";
import type { MatrixInsight } from "@/lib/bff/matrix-types";

function mkInsight(overrides: Partial<MatrixInsight> = {}): MatrixInsight {
  return {
    id: "i1",
    tenant_id: "t1",
    engagement_id: "e1",
    agent: "oracle",
    insight_type: "stale_commitment",
    severity: "high",
    title: "title",
    body: "body",
    citation_node_ids: [],
    citation_edge_ids: [],
    citation_event_ids: [],
    dedup_key: "k1",
    status: "open",
    created_at: "2026-05-01T00:00:00Z",
    decided_at: null,
    decided_by: null,
    ...overrides,
  };
}

describe("toGroupSeverity", () => {
  it("maps high to critical, medium to warning, low to info", () => {
    expect(toGroupSeverity("high")).toBe("critical");
    expect(toGroupSeverity("medium")).toBe("warning");
    expect(toGroupSeverity("low")).toBe("info");
  });
});

describe("humanizeKind", () => {
  it("converts snake_case to sentence case", () => {
    expect(humanizeKind("decision_cycle_slowdown")).toBe("Decision cycle slowdown");
  });
  it("handles single words", () => {
    expect(humanizeKind("risk")).toBe("Risk");
  });
  it("handles already-spaced kinds", () => {
    expect(humanizeKind("stale commitment")).toBe("Stale commitment");
  });
  it("handles kebab-case kinds", () => {
    expect(humanizeKind("missing-followup")).toBe("Missing followup");
  });
  it("handles empty strings", () => {
    expect(humanizeKind("")).toBe("");
  });
  it("collapses repeated separators", () => {
    expect(humanizeKind("foo__bar")).toBe("Foo bar");
  });
});

describe("isOpenByDefault", () => {
  function group(severityMax: InsightGroup["severityMax"]): InsightGroup {
    return { kind: "k", severityMax, insights: [] };
  }
  it("returns true for critical and warning", () => {
    expect(isOpenByDefault(group("critical"))).toBe(true);
    expect(isOpenByDefault(group("warning"))).toBe(true);
  });
  it("returns false for info", () => {
    expect(isOpenByDefault(group("info"))).toBe(false);
  });
});

describe("groupByKind", () => {
  it("returns 3 groups in severity order for 3 critical + 2 warning + 5 info", () => {
    const insights: MatrixInsight[] = [
      ...Array.from({ length: 3 }, (_, n) =>
        mkInsight({ id: `c${n}`, insight_type: "stale_commitment", severity: "high" }),
      ),
      ...Array.from({ length: 2 }, (_, n) =>
        mkInsight({ id: `w${n}`, insight_type: "decision_cycle_slowdown", severity: "medium" }),
      ),
      ...Array.from({ length: 5 }, (_, n) =>
        mkInsight({ id: `i${n}`, insight_type: "ambient_observation", severity: "low" }),
      ),
    ];
    const groups = groupByKind(insights);
    expect(groups).toHaveLength(3);
    expect(groups.map((g) => g.kind)).toEqual([
      "stale_commitment",
      "decision_cycle_slowdown",
      "ambient_observation",
    ]);
    expect(groups.map((g) => g.severityMax)).toEqual(["critical", "warning", "info"]);
    expect(groups.map((g) => g.insights.length)).toEqual([3, 2, 5]);
  });

  it("sorts insights within a group newest first", () => {
    const insights: MatrixInsight[] = [
      mkInsight({ id: "old", created_at: "2026-04-01T00:00:00Z" }),
      mkInsight({ id: "new", created_at: "2026-05-20T00:00:00Z" }),
      mkInsight({ id: "mid", created_at: "2026-05-01T00:00:00Z" }),
    ];
    const groups = groupByKind(insights);
    expect(groups).toHaveLength(1);
    const [only] = groups;
    expect(only?.insights.map((i) => i.id)).toEqual(["new", "mid", "old"]);
  });

  it("uses the max severity in a kind when severities are mixed", () => {
    const insights: MatrixInsight[] = [
      mkInsight({ id: "a", insight_type: "stale_commitment", severity: "low" }),
      mkInsight({ id: "b", insight_type: "stale_commitment", severity: "medium" }),
    ];
    const groups = groupByKind(insights);
    const [only] = groups;
    expect(only?.severityMax).toBe("warning");
  });

  it("returns an empty array for no insights", () => {
    expect(groupByKind([])).toEqual([]);
  });

  it("breaks ties on severity by alphabetical kind", () => {
    const insights: MatrixInsight[] = [
      mkInsight({ id: "z", insight_type: "zeta_alert", severity: "high" }),
      mkInsight({ id: "a", insight_type: "alpha_alert", severity: "high" }),
    ];
    const groups = groupByKind(insights);
    expect(groups.map((g) => g.kind)).toEqual(["alpha_alert", "zeta_alert"]);
  });
});
