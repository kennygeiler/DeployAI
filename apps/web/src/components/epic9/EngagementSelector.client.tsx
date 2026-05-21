"use client";

import * as React from "react";

import type { Engagement } from "@/lib/bff/engagement-types";

/**
 * Phase 1 — engagement scoping control. Lists the tenant's engagements from
 * `/api/bff/engagements`; the selection scopes the surface it sits on.
 * "All engagements" (empty value) means no engagement filter.
 */
export function EngagementSelector({
  value,
  onChange,
}: {
  value: string | undefined;
  onChange: (engagementId: string | undefined) => void;
}) {
  const [engagements, setEngagements] = React.useState<Engagement[]>([]);
  const [failed, setFailed] = React.useState(false);

  React.useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const r = await fetch("/api/bff/engagements", { cache: "no-store" });
        if (!r.ok) {
          if (active) setFailed(true);
          return;
        }
        const j = (await r.json()) as { engagements?: Engagement[] };
        if (active) {
          setEngagements(j.engagements ?? []);
          setFailed(false);
        }
      } catch {
        if (active) setFailed(true);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="flex items-center gap-2">
      <label htmlFor="engagement-selector" className="text-ink-700 text-sm font-medium">
        Engagement
      </label>
      <select
        id="engagement-selector"
        className="border-border rounded-md border px-2 py-1 text-sm"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value || undefined)}
      >
        <option value="">All engagements</option>
        {engagements.map((eng) => (
          <option key={eng.id} value={eng.id}>
            {eng.name}
          </option>
        ))}
      </select>
      {failed ? (
        <span role="status" className="text-destructive text-xs">
          Could not load engagements
        </span>
      ) : null}
    </div>
  );
}
