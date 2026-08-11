"use client";

import { ChevronDownIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { TimestampLabel } from "@/components/common/TimestampLabel.client";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import {
  groupByKind,
  humanizeKind,
  isOpenByDefault,
  type GroupSeverity,
  type InsightGroup,
} from "@/lib/bff/insight-grouping";
import type { UnifiedInsight } from "@/lib/bff/insight-types";
import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";

/**
 * Phase 7 (increment 7.3) + pilot-refresh F2 — the insights surface for one
 * engagement. Renders BOTH insight models through the unified BFF read path:
 * Oracle synthesis rows (`model: "matrix"`, Dismiss / Resolve / Explain) and
 * temporal analyzer rows (`model: "temporal"`, Snooze / Follow-up / Dismiss /
 * Resolve). Each action dispatches to the correct backend by model.
 *
 * Cards are observations, not graph edits — resolving does not mutate
 * the matrix. See `docs/product/synthesis-agents.md`.
 */
export type EngagementInsightsProps = {
  engagementId: string;
  // Stub for G1.c — per-card "Explain" button wires through to Agent Kenny.
  onExplain?: (insight: UnifiedInsight) => void;
};

const DEFAULT_SNOOZE_DAYS = 7;

function defaultFollowupDate(): string {
  const d = new Date();
  d.setDate(d.getDate() + 7);
  return d.toISOString().slice(0, 10);
}

export function EngagementInsights({ engagementId, onExplain }: EngagementInsightsProps) {
  const [insights, setInsights] = React.useState<UnifiedInsight[]>([]);
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
    const body = (await r.json()) as { insights?: UnifiedInsight[] };
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
      // Refresh re-runs the Oracle agent; re-list through the unified path so
      // temporal rows stay in the view.
      await fetchList();
      setErr(null);
      toast.success("Insights refreshed");
    } finally {
      setRefreshing(false);
    }
  }, [engagementId, fetchList]);

  const decide = React.useCallback(
    async (insight: UnifiedInsight, decision: "dismiss" | "resolve") => {
      setBusyId(insight.id);
      try {
        const model = insight.model === "temporal" ? "?model=temporal" : "";
        const r = await fetch(
          `/api/bff/engagements/${encodeURIComponent(engagementId)}/insights/` +
            `${encodeURIComponent(insight.id)}/${decision}${model}`,
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

  const snooze = React.useCallback(
    async (insight: UnifiedInsight) => {
      const raw =
        typeof window === "undefined"
          ? String(DEFAULT_SNOOZE_DAYS)
          : window.prompt("Snooze for how many days? (1-90)", String(DEFAULT_SNOOZE_DAYS));
      if (raw === null) {
        return;
      }
      const days = Number.parseInt(raw, 10);
      if (!Number.isInteger(days) || days < 1 || days > 90) {
        toast.error("Snooze needs a whole number of days between 1 and 90");
        return;
      }
      setBusyId(insight.id);
      try {
        const r = await fetch(
          `/api/bff/engagements/${encodeURIComponent(engagementId)}/insights/` +
            `${encodeURIComponent(insight.id)}/snooze`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ days }),
          },
        );
        if (!r.ok) {
          toast.error("Could not snooze insight", {
            description: (await readStrategistBffErrorDescription(r)).slice(0, 240),
          });
          return;
        }
        toast.success(`Snoozed for ${days} day(s)`);
        await fetchList();
      } finally {
        setBusyId(null);
      }
    },
    [engagementId, fetchList],
  );

  const followup = React.useCallback(
    async (insight: UnifiedInsight) => {
      const due =
        typeof window === "undefined"
          ? defaultFollowupDate()
          : window.prompt("Follow-up due date (YYYY-MM-DD)", defaultFollowupDate());
      if (due === null) {
        return;
      }
      if (!/^\d{4}-\d{2}-\d{2}$/.test(due)) {
        toast.error("Follow-up needs a YYYY-MM-DD due date");
        return;
      }
      setBusyId(insight.id);
      try {
        const r = await fetch(
          `/api/bff/engagements/${encodeURIComponent(engagementId)}/insights/` +
            `${encodeURIComponent(insight.id)}/followup`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            // owner_user_id is defaulted to the acting user server-side.
            body: JSON.stringify({ due_date: due }),
          },
        );
        if (!r.ok) {
          toast.error("Could not create follow-up", {
            description: (await readStrategistBffErrorDescription(r)).slice(0, 240),
          });
          return;
        }
        toast.success("Follow-up task created");
      } finally {
        setBusyId(null);
      }
    },
    [engagementId],
  );

  const groups = React.useMemo(() => groupByKind(insights), [insights]);

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
      {err ? <p className="text-red-ink text-sm">{err}</p> : null}
      {loading ? (
        <p className="text-ink-600 text-sm">Loading…</p>
      ) : insights.length === 0 ? (
        <p className="text-ink-600 text-sm">
          No insights yet — click <strong>Refresh insights</strong> to run the Oracle agent over
          this engagement&apos;s matrix.
        </p>
      ) : (
        <ul className="space-y-2">
          {groups.map((g) => (
            <li key={g.kind}>
              <InsightGroupSection
                group={g}
                busyId={busyId}
                onDecide={decide}
                onSnooze={snooze}
                onFollowup={followup}
                onExplain={onExplain}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function InsightGroupSection({
  group,
  busyId,
  onDecide,
  onSnooze,
  onFollowup,
  onExplain,
}: {
  group: InsightGroup<UnifiedInsight>;
  busyId: string | null;
  onDecide: (insight: UnifiedInsight, decision: "dismiss" | "resolve") => void;
  onSnooze: (insight: UnifiedInsight) => void;
  onFollowup: (insight: UnifiedInsight) => void;
  onExplain?: (insight: UnifiedInsight) => void;
}) {
  const [open, setOpen] = React.useState<boolean>(() => isOpenByDefault(group));
  const contentId = React.useId();
  return (
    <Collapsible open={open} onOpenChange={setOpen} className="rounded-card bg-surface shadow-card">
      <CollapsibleTrigger
        aria-controls={contentId}
        className="flex w-full items-center justify-between gap-3 rounded-card px-3 py-2 text-left transition-colors hover:bg-hover"
      >
        <span className="flex items-center gap-2">
          <SeverityBadge severity={group.severityMax} />
          <span className="text-sm font-medium text-ink">{humanizeKind(group.kind)}</span>
          <span
            className="rounded-full bg-hover px-1.5 py-0.5 font-mono text-[10px] text-ink-600 shadow-hairline"
            aria-label={`${group.insights.length} insight(s)`}
          >
            {group.insights.length}
          </span>
        </span>
        <ChevronDownIcon
          aria-hidden="true"
          className={
            "text-ink-600 size-4 transition-transform duration-200 " +
            (open ? "rotate-180" : "rotate-0")
          }
        />
      </CollapsibleTrigger>
      <CollapsibleContent id={contentId}>
        <ul className="divide-y divide-line border-t border-line text-sm">
          {group.insights.map((i) => (
            <li key={i.id} className="space-y-1 px-3 py-2">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2">
                  <InsightSeverityBadge severity={i.severity} />
                  <ModelBadge model={i.model} />
                  <TimestampLabel value={i.created_at} prefix="created" />
                </div>
                <div className="flex gap-1">
                  {onExplain ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      className="h-7 px-2 text-xs"
                      onClick={() => onExplain(i)}
                    >
                      Explain
                    </Button>
                  ) : null}
                  {i.model === "temporal" ? (
                    <>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="h-7 px-2 text-xs"
                        disabled={busyId === i.id}
                        onClick={() => onSnooze(i)}
                      >
                        Snooze
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="h-7 px-2 text-xs"
                        disabled={busyId === i.id}
                        onClick={() => onFollowup(i)}
                      >
                        Follow up
                      </Button>
                    </>
                  ) : null}
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="h-7 px-2 text-xs"
                    disabled={busyId === i.id}
                    onClick={() => onDecide(i, "resolve")}
                  >
                    Resolve
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="h-7 px-2 text-xs"
                    disabled={busyId === i.id}
                    onClick={() => onDecide(i, "dismiss")}
                  >
                    Dismiss
                  </Button>
                </div>
              </div>
              <p className="font-medium text-ink">{i.title}</p>
              <p className="whitespace-pre-line text-ink-600">{i.body}</p>
            </li>
          ))}
        </ul>
      </CollapsibleContent>
    </Collapsible>
  );
}

function SeverityBadge({ severity }: { severity: GroupSeverity }) {
  const classes =
    severity === "critical"
      ? "bg-red-tint text-red-ink"
      : severity === "warning"
        ? "bg-orange-tint text-orange-ink"
        : "bg-hover text-ink-600";
  return (
    <span
      className={`rounded-full px-1.5 py-0.5 font-mono text-[10px] uppercase shadow-hairline ${classes}`}
      aria-label={`severity ${severity}`}
    >
      {severity}
    </span>
  );
}

function InsightSeverityBadge({ severity }: { severity: UnifiedInsight["severity"] }) {
  const classes =
    severity === "high" || severity === "critical"
      ? "bg-red-tint text-red-ink"
      : severity === "medium"
        ? "bg-orange-tint text-orange-ink"
        : "bg-hover text-ink-600";
  return (
    <span
      className={`rounded-full px-1.5 py-0.5 font-mono text-[10px] uppercase shadow-hairline ${classes}`}
      aria-label={`severity ${severity}`}
    >
      {severity}
    </span>
  );
}

function ModelBadge({ model }: { model: UnifiedInsight["model"] }) {
  return (
    <span
      className="rounded-full bg-hover px-1.5 py-0.5 font-mono text-[10px] uppercase text-ink-600 shadow-hairline"
      aria-label={`source ${model === "matrix" ? "oracle" : "temporal"}`}
    >
      {model === "matrix" ? "oracle" : "temporal"}
    </span>
  );
}
