"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import type { MatrixInsight } from "@/lib/bff/matrix-types";
import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";

/**
 * Phase 7 (increment 7.3) — Oracle insights surface for one engagement.
 * Lists `open` insights (highest severity first), with a refresh button
 * that re-runs the Oracle agent and per-card Dismiss / Resolve buttons.
 *
 * Cards are observations, not graph edits — resolving does not mutate
 * the matrix. See `docs/product/synthesis-agents.md`.
 */
export function EngagementInsights({ engagementId }: { engagementId: string }) {
  const [insights, setInsights] = React.useState<MatrixInsight[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);
  const [busyId, setBusyId] = React.useState<string | null>(null);
  const [err, setErr] = React.useState<string | null>(null);

  const fetchList = React.useCallback(async () => {
    const r = await fetch(`/api/bff/engagements/${encodeURIComponent(engagementId)}/insights`, {
      cache: "no-store",
    });
    if (!r.ok) {
      setErr(await readStrategistBffErrorDescription(r));
      return;
    }
    setErr(null);
    const body = (await r.json()) as { insights?: MatrixInsight[] };
    setInsights(Array.isArray(body.insights) ? body.insights : []);
  }, [engagementId]);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        await fetchList();
      } catch (e) {
        // Surface as an in-card error rather than an unhandled rejection.
        // Real BFF errors hit the !r.ok branch above; this catches lower-level
        // failures (network, AbortError on unmount, test-env fetch teardown).
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : "Could not load insights.");
        }
      }
      if (!cancelled) {
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [fetchList]);

  const refresh = React.useCallback(async () => {
    setRefreshing(true);
    try {
      const r = await fetch(
        `/api/bff/engagements/${encodeURIComponent(engagementId)}/insights/refresh`,
        { method: "POST" },
      );
      if (!r.ok) {
        toast.error("Could not refresh insights", {
          description: (await readStrategistBffErrorDescription(r)).slice(0, 240),
        });
        return;
      }
      const body = (await r.json()) as { insights?: MatrixInsight[] };
      const list = Array.isArray(body.insights) ? body.insights : [];
      setInsights(list);
      toast.success(`Refreshed — ${list.length} open insight(s)`);
    } finally {
      setRefreshing(false);
    }
  }, [engagementId]);

  const decide = React.useCallback(
    async (insightId: string, decision: "dismiss" | "resolve") => {
      setBusyId(insightId);
      try {
        const r = await fetch(
          `/api/bff/engagements/${encodeURIComponent(engagementId)}/insights/` +
            `${encodeURIComponent(insightId)}/${decision}`,
          { method: "POST" },
        );
        if (!r.ok) {
          toast.error(
            decision === "dismiss" ? "Could not dismiss insight" : "Could not resolve insight",
            { description: (await readStrategistBffErrorDescription(r)).slice(0, 240) },
          );
          return;
        }
        toast.success(decision === "dismiss" ? "Dismissed" : "Marked resolved");
        await fetchList();
      } finally {
        setBusyId(null);
      }
    },
    [engagementId, fetchList],
  );

  return (
    <section aria-labelledby="engagement-insights-heading" className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h2 id="engagement-insights-heading" className="text-base font-semibold">
          Insights
        </h2>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => void refresh()}
          disabled={refreshing}
        >
          {refreshing ? "Refreshing…" : "Refresh insights"}
        </Button>
      </div>
      {err ? <p className="text-error-700 text-sm">{err}</p> : null}
      {loading ? (
        <p className="text-ink-600 text-sm">Loading…</p>
      ) : insights.length === 0 ? (
        <p className="text-ink-600 text-sm">
          No insights yet — click <strong>Refresh insights</strong> to run the Oracle agent over
          this engagement&apos;s matrix.
        </p>
      ) : (
        <ul className="border-border divide-border divide-y rounded-lg border text-sm">
          {insights.map((i) => (
            <li key={i.id} className="space-y-1 px-3 py-2">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2">
                  <SeverityBadge severity={i.severity} />
                  <span className="text-ink-600 font-mono text-xs uppercase">
                    {i.insight_type.replace(/_/g, " ")}
                  </span>
                </div>
                <div className="flex gap-1">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="h-7 px-2 text-xs"
                    disabled={busyId === i.id}
                    onClick={() => void decide(i.id, "resolve")}
                  >
                    Resolve
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="h-7 px-2 text-xs"
                    disabled={busyId === i.id}
                    onClick={() => void decide(i.id, "dismiss")}
                  >
                    Dismiss
                  </Button>
                </div>
              </div>
              <p className="text-ink-900 font-medium">{i.title}</p>
              <p className="text-ink-700 whitespace-pre-line">{i.body}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function SeverityBadge({ severity }: { severity: MatrixInsight["severity"] }) {
  const classes =
    severity === "high"
      ? "bg-error-100 text-error-900"
      : severity === "medium"
        ? "bg-warning-100 text-warning-900"
        : "bg-ink-100 text-ink-800";
  return (
    <span
      className={`rounded px-1.5 py-0.5 font-mono text-[10px] uppercase ${classes}`}
      aria-label={`severity ${severity}`}
    >
      {severity}
    </span>
  );
}
