import type { MatrixInsight } from "@/lib/bff/matrix-types";

export type GroupSeverity = "critical" | "warning" | "info";

export type InsightGroup = {
  kind: string;
  severityMax: GroupSeverity;
  insights: MatrixInsight[];
};

const SEVERITY_RANK: Record<GroupSeverity, number> = {
  critical: 3,
  warning: 2,
  info: 1,
};

export function toGroupSeverity(severity: MatrixInsight["severity"]): GroupSeverity {
  if (severity === "high") return "critical";
  if (severity === "medium") return "warning";
  return "info";
}

export function humanizeKind(kind: string): string {
  if (kind.length === 0) return kind;
  const spaced = kind.replace(/[_-]+/g, " ").trim();
  if (spaced.length === 0) return spaced;
  return spaced.charAt(0).toUpperCase() + spaced.slice(1).toLowerCase();
}

export function isOpenByDefault(group: InsightGroup): boolean {
  return group.severityMax !== "info";
}

export function groupByKind(insights: MatrixInsight[]): InsightGroup[] {
  const buckets = new Map<string, MatrixInsight[]>();
  for (const insight of insights) {
    const list = buckets.get(insight.insight_type);
    if (list) {
      list.push(insight);
    } else {
      buckets.set(insight.insight_type, [insight]);
    }
  }

  const groups: InsightGroup[] = [];
  for (const [kind, list] of buckets) {
    const sorted = [...list].sort((a, b) => compareCreatedAtDesc(a.created_at, b.created_at));
    const severityMax = sorted.reduce<GroupSeverity>((acc, item) => {
      const cur = toGroupSeverity(item.severity);
      return SEVERITY_RANK[cur] > SEVERITY_RANK[acc] ? cur : acc;
    }, "info");
    groups.push({ kind, severityMax, insights: sorted });
  }

  groups.sort((a, b) => {
    const sevDiff = SEVERITY_RANK[b.severityMax] - SEVERITY_RANK[a.severityMax];
    if (sevDiff !== 0) return sevDiff;
    return a.kind.localeCompare(b.kind);
  });

  return groups;
}

function compareCreatedAtDesc(a: string, b: string): number {
  const ta = Date.parse(a);
  const tb = Date.parse(b);
  const va = Number.isNaN(ta) ? 0 : ta;
  const vb = Number.isNaN(tb) ? 0 : tb;
  return vb - va;
}
