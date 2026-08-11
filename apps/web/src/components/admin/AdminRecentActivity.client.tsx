"use client";

import * as React from "react";

import { RecentActivityStrip } from "@/components/engagements/RecentActivityStrip.client";
import type { Engagement } from "@/lib/bff/engagement-types";

/**
 * Wave 2.5 U3 — the agent-telemetry activity strip, re-homed from the
 * engagement Brief to the admin dashboard. Admins pick an engagement; the
 * strip shows its latest ledger events (including agent tool invocations).
 */
export function AdminRecentActivity() {
  const [engagements, setEngagements] = React.useState<Engagement[]>([]);
  const [selectedId, setSelectedId] = React.useState<string>("");
  const [loaded, setLoaded] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const r = await fetch("/api/bff/engagements", { cache: "no-store" });
        if (!r.ok || cancelled) return;
        const body = (await r.json()) as { engagements?: Engagement[] };
        if (cancelled) return;
        const list = Array.isArray(body.engagements) ? body.engagements : [];
        setEngagements(list);
        if (list.length > 0) {
          setSelectedId(list[0]!.id);
        }
      } catch {
        // Section degrades to its empty state.
      } finally {
        if (!cancelled) setLoaded(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section aria-labelledby="admin-recent-activity-heading" className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="admin-recent-activity-heading" className="text-base font-semibold">
          Recent engagement activity
        </h2>
        {engagements.length > 0 ? (
          <div className="grid gap-1">
            <label className="sr-only" htmlFor="admin-activity-engagement">
              Engagement
            </label>
            <select
              id="admin-activity-engagement"
              className="rounded-control border border-transparent bg-field px-2 py-1 text-sm shadow-inset-field outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
              value={selectedId}
              onChange={(e) => setSelectedId(e.target.value)}
            >
              {engagements.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.name}
                </option>
              ))}
            </select>
          </div>
        ) : null}
      </div>
      {loaded && engagements.length === 0 ? (
        <p className="text-ink-600 text-sm">
          No engagements yet — the activity strip lights up once the first deal exists.
        </p>
      ) : null}
      {selectedId ? <RecentActivityStrip key={selectedId} engagementId={selectedId} /> : null}
    </section>
  );
}
