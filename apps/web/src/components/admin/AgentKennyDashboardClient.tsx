"use client";

import * as React from "react";

import { Button } from "@/components/ui/button";
import {
  AgentKennyDashboardSchema,
  WINDOW_DAYS_DEFAULT,
  type AgentKennyDashboard,
  type LintFlagCount,
  type ToolCallCount,
  type TopCitedEvent,
} from "@/lib/internal/agent-kenny-dashboard-cp";

/**
 * Phase 6 Wave C — interactive shell for the Agent Kenny telemetry
 * dashboard.
 *
 * Server page hands us ``initialData`` so the first paint has the 7-day
 * snapshot (or a friendly empty-state if the CP is unreachable). After
 * that, the window selector + the 60s auto-refresh both re-fetch via
 * the BFF, which in turn calls the tenant-scoped CP route.
 *
 * Charting: we draw a small horizontal bar chart for tool-call counts
 * with inline SVG. Adding `recharts` for one chart this small was not
 * worth the bundle weight (none of the other admin pages pull a chart
 * library today) — if a second chart shows up in a future wave we can
 * factor a shared primitive.
 */

const REFRESH_INTERVAL_MS = 60_000;
const WINDOW_OPTIONS: readonly { days: number; label: string }[] = [
  { days: 1, label: "1 day" },
  { days: 7, label: "7 days" },
  { days: 30, label: "30 days" },
];

export type AgentKennyDashboardClientProps = {
  tenantId: string | null;
  initialData: AgentKennyDashboard | null;
  initialError: string | null;
};

export function AgentKennyDashboardClient(props: AgentKennyDashboardClientProps) {
  const { tenantId, initialData, initialError } = props;
  const [windowDays, setWindowDays] = React.useState<number>(
    initialData?.window_days ?? WINDOW_DAYS_DEFAULT,
  );
  const [data, setData] = React.useState<AgentKennyDashboard | null>(initialData);
  const [error, setError] = React.useState<string | null>(initialError);
  const [loading, setLoading] = React.useState(false);
  const [autoRefresh, setAutoRefresh] = React.useState(true);

  const load = React.useCallback(
    async (days: number) => {
      if (!tenantId) {
        setError("No tenant id on the current actor — can't load telemetry.");
        return;
      }
      setLoading(true);
      try {
        const url = `/api/internal/v1/tenants/${encodeURIComponent(tenantId)}/agent_kenny_dashboard?window_days=${days}`;
        const r = await fetch(url, { cache: "no-store" });
        if (!r.ok) {
          setError(`Could not load dashboard (${r.status})`);
          return;
        }
        const parsed = AgentKennyDashboardSchema.safeParse(await r.json());
        if (!parsed.success) {
          setError("Could not parse dashboard response");
          return;
        }
        setError(null);
        setData(parsed.data);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not load dashboard.");
      } finally {
        setLoading(false);
      }
    },
    [tenantId],
  );

  const onWindowChange = React.useCallback(
    (days: number) => {
      setWindowDays(days);
      void load(days);
    },
    [load],
  );

  React.useEffect(() => {
    if (!autoRefresh) return;
    const id = window.setInterval(() => {
      void load(windowDays);
    }, REFRESH_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [autoRefresh, load, windowDays]);

  return (
    <section
      aria-labelledby="agent-kenny-dashboard-heading"
      className="space-y-6"
      data-testid="agent-kenny-dashboard"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="agent-kenny-dashboard-heading" className="sr-only">
          Agent Kenny dashboard
        </h2>
        <WindowSelector value={windowDays} onChange={onWindowChange} disabled={loading} />
        <div className="flex items-center gap-2">
          <label className="text-ink-700 flex items-center gap-1.5 text-xs">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              data-testid="agent-kenny-dashboard-auto-refresh"
            />
            Auto-refresh (60s)
          </label>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => void load(windowDays)}
            disabled={loading}
            data-testid="agent-kenny-dashboard-refresh"
          >
            {loading ? "Refreshing…" : "Refresh"}
          </Button>
        </div>
      </div>

      {error ? (
        <p role="alert" className="text-error-700 text-sm">
          {error}
        </p>
      ) : null}

      {data ? (
        <>
          <MetricCards data={data} />
          <ToolCallChart tools={data.tool_calls} />
          <LintFlagTable rows={data.lint_flag_counts} />
          <TopCitedEventsTable rows={data.top_cited_events} />
        </>
      ) : (
        <p
          className="text-ink-600 border-border bg-paper-50 rounded-md border px-3 py-6 text-center text-sm"
          data-testid="agent-kenny-dashboard-empty"
        >
          No telemetry yet in this window.
        </p>
      )}
    </section>
  );
}

function WindowSelector(props: {
  value: number;
  onChange: (days: number) => void;
  disabled: boolean;
}) {
  return (
    <div
      role="group"
      aria-label="Window selector"
      className="border-border inline-flex rounded-md border"
      data-testid="agent-kenny-dashboard-window-selector"
    >
      {WINDOW_OPTIONS.map((opt) => {
        const active = opt.days === props.value;
        return (
          <Button
            key={opt.days}
            type="button"
            variant="ghost"
            size="sm"
            aria-pressed={active}
            disabled={props.disabled}
            onClick={() => props.onChange(opt.days)}
            data-testid={`agent-kenny-dashboard-window-${opt.days}`}
            className={
              "rounded-none first:rounded-l-md last:rounded-r-md " +
              (active ? "bg-paper-200 text-ink-950" : "text-ink-700")
            }
          >
            {opt.label}
          </Button>
        );
      })}
    </div>
  );
}

export function hallucinationTrafficLight(rate: number): {
  cls: string;
  level: "green" | "amber" | "red";
} {
  // Thresholds: <2% green, 2–5% amber, >5% red (scope-v2 §11.4 / spec).
  if (rate > 0.05) return { cls: "bg-error-100 text-error-900", level: "red" };
  if (rate >= 0.02) return { cls: "bg-amber-100 text-amber-900", level: "amber" };
  return { cls: "bg-emerald-100 text-emerald-900", level: "green" };
}

function MetricCards(props: { data: AgentKennyDashboard }) {
  const { data } = props;
  const halluc = hallucinationTrafficLight(data.hallucination_rate);
  return (
    <div
      className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4"
      data-testid="agent-kenny-dashboard-cards"
    >
      <MetricCard
        label="Hallucination rate"
        testId="agent-kenny-dashboard-card-hallucination"
        data-traffic-light={halluc.level}
      >
        <span
          className={`inline-flex items-baseline rounded px-2 py-0.5 text-2xl font-semibold ${halluc.cls}`}
          data-testid="agent-kenny-dashboard-hallucination-value"
        >
          {(data.hallucination_rate * 100).toFixed(1)}%
        </span>
        <p className="text-ink-600 mt-1 text-xs">
          {data.citations_unverified.toLocaleString()} / {data.citations_total.toLocaleString()}{" "}
          unverified
        </p>
      </MetricCard>

      <MetricCard label="Latency (p50 / p95 / p99)" testId="agent-kenny-dashboard-card-latency">
        <p className="text-ink-900 font-mono text-lg">
          {data.latency_p50_ms} / {data.latency_p95_ms} /{" "}
          <span data-testid="agent-kenny-dashboard-latency-p99">{data.latency_p99_ms}</span>
          <span className="text-ink-600 text-xs"> ms</span>
        </p>
      </MetricCard>

      <MetricCard label='"I don’t know" rate' testId="agent-kenny-dashboard-card-idk">
        <p className="text-ink-900 text-2xl font-semibold">{(data.idk_rate * 100).toFixed(1)}%</p>
        <p className="text-ink-600 mt-1 text-xs">turns refusing the question</p>
      </MetricCard>

      <MetricCard label="Adversarial concerns" testId="agent-kenny-dashboard-card-adversarial">
        <p className="text-ink-900 text-2xl font-semibold">
          {data.adversarial_concerns_total.toLocaleString()}
        </p>
        <p className="text-ink-600 mt-1 text-xs">concerns flagged by adversarial review</p>
      </MetricCard>
    </div>
  );
}

function MetricCard(
  props: React.PropsWithChildren<{ label: string; testId: string; "data-traffic-light"?: string }>,
) {
  return (
    <div
      className="border-border bg-paper-50 rounded-md border p-3"
      data-testid={props.testId}
      data-traffic-light={props["data-traffic-light"]}
    >
      <h3 className="text-ink-600 text-xs font-medium uppercase tracking-wide">{props.label}</h3>
      <div className="mt-2">{props.children}</div>
    </div>
  );
}

function ToolCallChart(props: { tools: ToolCallCount[] }) {
  if (props.tools.length === 0) {
    return (
      <Section title="Tool-call distribution" testId="agent-kenny-dashboard-tools">
        <EmptyState>No tool calls in this window.</EmptyState>
      </Section>
    );
  }
  const max = Math.max(...props.tools.map((t) => t.count), 1);
  const ROW_H = 22;
  const PAD_LEFT = 140;
  const PAD_RIGHT = 50;
  const PAD_TOP = 8;
  const PAD_BOT = 8;
  const W = 560;
  const H = PAD_TOP + PAD_BOT + props.tools.length * ROW_H;
  const barWidth = (count: number) => Math.max(2, ((W - PAD_LEFT - PAD_RIGHT) * count) / max);
  return (
    <Section title="Tool-call distribution" testId="agent-kenny-dashboard-tools">
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label="Tool-call counts bar chart"
          className="block w-full"
        >
          {props.tools.map((t, i) => {
            const y = PAD_TOP + i * ROW_H;
            const bw = barWidth(t.count);
            return (
              <g key={t.tool} data-testid={`agent-kenny-dashboard-tool-row-${t.tool}`}>
                <text
                  x={PAD_LEFT - 6}
                  y={y + ROW_H / 2}
                  textAnchor="end"
                  dominantBaseline="middle"
                  className="fill-ink-800 font-mono text-[11px]"
                >
                  {t.tool}
                </text>
                <rect
                  x={PAD_LEFT}
                  y={y + 4}
                  width={bw}
                  height={ROW_H - 8}
                  rx={2}
                  className="fill-emerald-400"
                />
                <text
                  x={PAD_LEFT + bw + 4}
                  y={y + ROW_H / 2}
                  textAnchor="start"
                  dominantBaseline="middle"
                  className="fill-ink-700 text-[11px]"
                >
                  {t.count}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </Section>
  );
}

function LintFlagTable(props: { rows: LintFlagCount[] }) {
  if (props.rows.length === 0) {
    return (
      <Section title="Lint flag breakdown" testId="agent-kenny-dashboard-lint">
        <EmptyState>No lint flags raised in this window.</EmptyState>
      </Section>
    );
  }
  return (
    <Section title="Lint flag breakdown" testId="agent-kenny-dashboard-lint">
      <div className="border-border overflow-x-auto rounded-md border">
        <table className="w-full text-sm">
          <thead className="bg-surface-subtle text-ink-700 text-xs uppercase">
            <tr>
              <th className="px-3 py-2 text-left">Kind</th>
              <th className="px-3 py-2 text-right">Count</th>
              <th className="px-3 py-2 text-left">Most recent</th>
            </tr>
          </thead>
          <tbody className="divide-border divide-y">
            {props.rows.map((row) => (
              <tr key={row.kind} data-testid={`agent-kenny-dashboard-lint-row-${row.kind}`}>
                <td className="px-3 py-2 font-mono text-xs">{row.kind}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{row.count}</td>
                <td className="text-ink-700 px-3 py-2 font-mono text-xs">
                  {row.most_recent ? new Date(row.most_recent).toISOString() : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function TopCitedEventsTable(props: { rows: TopCitedEvent[] }) {
  if (props.rows.length === 0) {
    return (
      <Section title="Top-cited events" testId="agent-kenny-dashboard-top-cited">
        <EmptyState>No citations yet in this window.</EmptyState>
      </Section>
    );
  }
  return (
    <Section title="Top-cited events" testId="agent-kenny-dashboard-top-cited">
      <div className="border-border overflow-x-auto rounded-md border">
        <table className="w-full text-sm">
          <thead className="bg-surface-subtle text-ink-700 text-xs uppercase">
            <tr>
              <th className="px-3 py-2 text-left">Summary</th>
              <th className="px-3 py-2 text-right">Citations</th>
              <th className="px-3 py-2 text-left">Event id</th>
            </tr>
          </thead>
          <tbody className="divide-border divide-y">
            {props.rows.map((row) => (
              <tr
                key={row.event_id}
                data-testid={`agent-kenny-dashboard-cited-row-${row.event_id}`}
              >
                <td className="text-ink-800 px-3 py-2 text-xs">{row.summary || "(no summary)"}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{row.citation_count}</td>
                <td className="text-ink-600 px-3 py-2 font-mono text-[10px]">{row.event_id}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function Section(props: React.PropsWithChildren<{ title: string; testId: string }>) {
  return (
    <section aria-label={props.title} className="space-y-2" data-testid={props.testId}>
      <h3 className="text-ink-900 text-sm font-semibold">{props.title}</h3>
      {props.children}
    </section>
  );
}

function EmptyState(props: React.PropsWithChildren) {
  return (
    <p className="text-ink-600 border-border bg-paper-50 rounded-md border px-3 py-4 text-center text-xs">
      {props.children}
    </p>
  );
}
