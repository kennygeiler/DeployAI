"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import type { MatrixInsight } from "@/lib/bff/matrix-types";
import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";

/**
 * Phase 7 (increment 7.4) — Master Strategist insights across the whole
 * tenant portfolio. Lists `open` cross-engagement insights (recurring
 * risk patterns, system concentration, role-coverage gaps), with a
 * refresh button + per-card Dismiss / Resolve buttons.
 *
 * Sits at the top of the `/engagements` (portfolio) page. Same card
 * shape as EngagementInsights — only the data source differs (tenant
 * scope vs single-engagement scope).
 *
 * See `docs/product/synthesis-agents.md` §4.
 */
export function PortfolioInsights() {
  const [insights, setInsights] = React.useState<MatrixInsight[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);
  const [busyId, setBusyId] = React.useState<string | null>(null);
  const [err, setErr] = React.useState<string | null>(null);

  const fetchList = React.useCallback(async () => {
    const r = await fetch("/api/bff/portfolio/insights", { cache: "no-store" });
    if (!r.ok) {
      setErr(await readStrategistBffErrorDescription(r));
      return;
    }
    setErr(null);
    const body = (await r.json()) as { insights?: MatrixInsight[] };
    setInsights(Array.isArray(body.insights) ? body.insights : []);
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        await fetchList();
      } catch (e) {
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : "Could not load portfolio insights.");
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
      const r = await fetch("/api/bff/portfolio/insights/refresh", { method: "POST" });
      if (!r.ok) {
        toast.error("Could not refresh portfolio insights", {
          description: (await readStrategistBffErrorDescription(r)).slice(0, 240),
        });
        return;
      }
      const body = (await r.json()) as { insights?: MatrixInsight[] };
      const list = Array.isArray(body.insights) ? body.insights : [];
      setInsights(list);
      toast.success(`Refreshed — ${list.length} open portfolio insight(s)`);
    } finally {
      setRefreshing(false);
    }
  }, []);

  const decide = React.useCallback(
    async (insightId: string, decision: "dismiss" | "resolve") => {
      setBusyId(insightId);
      try {
        const r = await fetch(
          `/api/bff/portfolio/insights/${encodeURIComponent(insightId)}/${decision}`,
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
    [fetchList],
  );

  return (
    <section aria-labelledby="portfolio-insights-heading" className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h2 id="portfolio-insights-heading" className="text-base font-semibold">
          Portfolio insights
        </h2>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => void refresh()}
          disabled={refreshing}
        >
          {refreshing ? "Refreshing…" : "Refresh portfolio insights"}
        </Button>
      </div>
      {err ? <p className="text-error-700 text-sm">{err}</p> : null}
      {loading ? (
        <p className="text-ink-600 text-sm">Loading…</p>
      ) : insights.length === 0 ? (
        <p className="text-ink-600 text-sm">
          No portfolio insights yet — click <strong>Refresh portfolio insights</strong> to run the
          Master Strategist agent across your engagements.
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
