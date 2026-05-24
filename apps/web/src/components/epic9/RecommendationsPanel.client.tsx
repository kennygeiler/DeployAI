"use client";

import * as React from "react";

import type {
  Recommendation,
  RecommendationPriority,
  RecommendationRole,
} from "@/lib/internal/recommendations-cp";

import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";

const ROLE_LABEL: Record<RecommendationRole, string> = {
  fde: "FDE",
  deployment_strategist: "Strategist",
  biz_dev: "BizDev",
};

const PRIORITY_ORDER: RecommendationPriority[] = ["high", "medium", "low"];

const PRIORITY_GROUP_LABEL: Record<RecommendationPriority, string> = {
  high: "High priority",
  medium: "Medium priority",
  low: "Low priority",
};

/**
 * Sprint 3.2 — deterministic "Recommended next actions" panel. Each card is
 * a predicate-fired recommendation tagged with the role responsible and
 * a priority. Cards are grouped by priority (high → medium → low).
 */
export function RecommendationsPanel({ engagementId }: { engagementId: string }) {
  const [recommendations, setRecommendations] = React.useState<Recommendation[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [err, setErr] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const r = await fetch(
          `/api/bff/engagements/${encodeURIComponent(engagementId)}/recommendations`,
          { cache: "no-store" },
        );
        if (cancelled) {
          return;
        }
        if (!r.ok) {
          setErr(await readStrategistBffErrorDescription(r));
          return;
        }
        const body = (await r.json()) as { recommendations?: Recommendation[] };
        setErr(null);
        setRecommendations(Array.isArray(body.recommendations) ? body.recommendations : []);
      } catch (e) {
        // Catch low-level fetch failures (network, AbortError on unmount,
        // test teardown leaks) so they don't surface as unhandled rejections.
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : "Could not load recommendations.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [engagementId]);

  const grouped = React.useMemo(() => {
    const buckets: Record<RecommendationPriority, Recommendation[]> = {
      high: [],
      medium: [],
      low: [],
    };
    for (const r of recommendations) {
      if (r.priority in buckets) {
        buckets[r.priority].push(r);
      }
    }
    return buckets;
  }, [recommendations]);

  return (
    <section aria-labelledby="engagement-recommendations-heading" className="space-y-3">
      <h2 id="engagement-recommendations-heading" className="text-ink-800 text-sm font-semibold">
        Recommended next actions
      </h2>
      {err ? <p className="text-error-700 text-sm">{err}</p> : null}
      {loading ? (
        <p className="text-ink-600 text-sm">Loading…</p>
      ) : err ? null : recommendations.length === 0 ? (
        <p className="text-ink-600 text-sm">
          No outstanding actions — the matrix is in a good state.
        </p>
      ) : (
        <div className="space-y-4">
          {PRIORITY_ORDER.map((p) => {
            const items = grouped[p];
            if (items.length === 0) {
              return null;
            }
            return (
              <div key={p} className="space-y-2">
                <h3 className="text-ink-700 text-xs font-semibold uppercase">
                  {PRIORITY_GROUP_LABEL[p]}
                </h3>
                <ul className="border-border divide-border divide-y rounded-lg border text-sm">
                  {items.map((rec) => (
                    <li key={rec.id} className="space-y-1 px-3 py-2">
                      <div className="flex items-center gap-2">
                        <RoleBadge role={rec.role} />
                        <PriorityBadge priority={rec.priority} />
                      </div>
                      <p className="text-ink-900 font-medium">{rec.title}</p>
                      <p className="text-ink-700 whitespace-pre-line">{rec.body}</p>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

function RoleBadge({ role }: { role: RecommendationRole }) {
  return (
    <span
      className="bg-ink-100 text-ink-800 rounded px-1.5 py-0.5 font-mono text-[10px] uppercase"
      aria-label={`role ${role}`}
    >
      {ROLE_LABEL[role] ?? role}
    </span>
  );
}

function PriorityBadge({ priority }: { priority: RecommendationPriority }) {
  const classes =
    priority === "high"
      ? "bg-error-100 text-error-900"
      : priority === "medium"
        ? "bg-warning-100 text-warning-900"
        : "bg-ink-100 text-ink-800";
  return (
    <span
      className={`rounded px-1.5 py-0.5 font-mono text-[10px] uppercase ${classes}`}
      aria-label={`priority ${priority}`}
    >
      {priority}
    </span>
  );
}
