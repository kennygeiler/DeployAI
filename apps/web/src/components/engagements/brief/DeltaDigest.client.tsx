"use client";

import * as React from "react";

import { TimestampLabel } from "@/components/common/TimestampLabel.client";
import type { EngagementSummaryChange } from "@/lib/bff/summary-types";
import {
  BUCKET_LABEL,
  sourceKindBucket,
  stripRedundantKindPrefix,
  type SourceKindBucket,
} from "@/lib/labels";

/**
 * Wave 2.5 U3 — "Since you last looked": the recent-change feed from the
 * summary endpoint, grouped by bucket with human titles.
 *
 * TODO(F1): this slot is the future home of the real delta digest —
 * snapshot-diff "since your last visit / this week" rollups (new
 * stakeholders/decisions/risks/commitments + silence flags) instead of the
 * raw recent-change feed. Keep the component name and mount point; swap the
 * data source when F1 lands.
 */

const BUCKET_ORDER: readonly SourceKindBucket[] = [
  "decision",
  "risk",
  "commitment",
  "stakeholder",
  "proposal",
  "agent",
  "system",
  "other",
];

export function DeltaDigest({
  changes,
  loading = false,
}: {
  changes: EngagementSummaryChange[];
  loading?: boolean;
}) {
  const groups = React.useMemo(() => {
    const byBucket = new Map<SourceKindBucket, EngagementSummaryChange[]>();
    for (const change of changes) {
      const bucket = sourceKindBucket(change.kind);
      const list = byBucket.get(bucket);
      if (list) {
        list.push(change);
      } else {
        byBucket.set(bucket, [change]);
      }
    }
    return BUCKET_ORDER.filter((b) => byBucket.has(b)).map((b) => ({
      bucket: b,
      changes: byBucket.get(b)!,
    }));
  }, [changes]);

  return (
    <section aria-labelledby="delta-digest-heading" data-testid="delta-digest" className="space-y-2">
      <h2 id="delta-digest-heading" className="text-ink-800 text-sm font-semibold">
        Since you last looked
      </h2>
      {loading ? (
        <p className="text-ink-600 text-sm">Loading recent changes…</p>
      ) : groups.length === 0 ? (
        <p className="text-ink-600 text-sm" data-testid="delta-digest-empty">
          Nothing new on this deal yet. Changes land here as emails, meetings, and notes are
          imported — drop an interaction in the Capture tab to get things moving.
        </p>
      ) : (
        <div className="space-y-3 rounded-card bg-surface p-3 shadow-card">
          {groups.map((g) => (
            <div key={g.bucket} data-testid={`delta-digest-group-${g.bucket}`}>
              <h3 className="text-ink-600 text-xs font-semibold uppercase tracking-wide">
                {BUCKET_LABEL[g.bucket]}
              </h3>
              <ul className="mt-1 space-y-1">
                {g.changes.map((c, i) => (
                  <li
                    key={`${c.occurred_at}-${i}`}
                    className="flex flex-wrap items-baseline gap-x-2 text-sm"
                  >
                    <span className="text-ink-800">
                      {stripRedundantKindPrefix(c.title, c.kind)}
                    </span>
                    {c.actor_display_name ? (
                      <span className="text-ink-500 text-xs">by {c.actor_display_name}</span>
                    ) : null}
                    <TimestampLabel value={c.occurred_at} className="text-ink-500" />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
