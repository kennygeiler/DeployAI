"use client";

import * as React from "react";

import { Button } from "@/components/ui/button";
import { EvalRunListSchema, type EvalRun } from "@/lib/internal/eval-runs-cp";

/**
 * Wave 4 (G8) — "Eval history" section for the Agent Kenny admin
 * dashboard.
 *
 * Renders the recorded golden-eval runs (newest first) as a small table
 * plus a compact pass-rate sparkline, so quality trends (pass rate,
 * hallucination rate, cross-engagement leaks) are visible over time
 * rather than only per-run in CI logs.
 *
 * Server page hands us the initial list; the refresh button re-fetches
 * via the admin BFF (``/api/bff/admin/eval-runs``). Charting follows the
 * dashboard's existing inline-SVG pattern (see ``ToolCallChart`` in
 * ``AgentKennyDashboardClient``) — no chart library.
 */

const LIST_LIMIT = 50;

export type EvalHistorySectionProps = {
  initialRuns: EvalRun[] | null;
  initialError: string | null;
};

export function EvalHistorySection(props: EvalHistorySectionProps) {
  const [runs, setRuns] = React.useState<EvalRun[] | null>(props.initialRuns);
  const [error, setError] = React.useState<string | null>(props.initialError);
  const [loading, setLoading] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`/api/bff/admin/eval-runs?limit=${LIST_LIMIT}`, {
        cache: "no-store",
      });
      if (!r.ok) {
        setError(`Could not load eval history (${r.status})`);
        return;
      }
      const parsed = EvalRunListSchema.safeParse(await r.json());
      if (!parsed.success) {
        setError("Could not parse eval history response");
        return;
      }
      setError(null);
      setRuns(parsed.data.runs);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load eval history.");
    } finally {
      setLoading(false);
    }
  }, []);

  return (
    <section aria-label="Eval history" className="space-y-2" data-testid="eval-history">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-ink">Eval history</h3>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => void load()}
          disabled={loading}
          data-testid="eval-history-refresh"
        >
          {loading ? "Refreshing…" : "Refresh"}
        </Button>
      </div>

      {error ? (
        <p role="alert" className="text-sm text-red-ink">
          {error}
        </p>
      ) : null}

      {runs && runs.length > 0 ? (
        <>
          <PassRateSparkline runs={runs} />
          <EvalRunTable runs={runs} />
        </>
      ) : (
        <p
          className="rounded-card bg-surface px-3 py-6 text-center text-xs text-ink-600 shadow-card"
          data-testid="eval-history-empty"
        >
          No eval runs recorded yet. Runs land here when the golden eval runner is invoked with{" "}
          <code className="font-mono">--persist-url</code> pointing at the control plane (it POSTs
          its report JSON to <code className="font-mono">/internal/v1/admin/eval-runs</code>).
        </p>
      )}
    </section>
  );
}

/**
 * Compact inline-SVG sparkline of pass_rate over time (oldest → newest,
 * left → right). The y-axis is the full 0–100% range so a run-to-run
 * regression reads as a visible dip rather than autoscaled noise.
 */
function PassRateSparkline(props: { runs: EvalRun[] }) {
  // The API returns newest-first; the sparkline reads oldest → newest.
  const chronological = [...props.runs].reverse();
  const W = 560;
  const H = 56;
  const PAD_X = 6;
  const PAD_Y = 6;
  const latest = chronological[chronological.length - 1];
  if (!latest) return null;
  const x = (i: number) =>
    chronological.length === 1 ? W / 2 : PAD_X + ((W - 2 * PAD_X) * i) / (chronological.length - 1);
  const y = (rate: number) => PAD_Y + (H - 2 * PAD_Y) * (1 - rate);
  const points = chronological.map((run, i) => `${x(i).toFixed(1)},${y(run.pass_rate).toFixed(1)}`);
  return (
    <div className="overflow-x-auto rounded-card bg-surface p-2 shadow-card">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`Pass rate over the last ${chronological.length} eval runs; latest ${(latest.pass_rate * 100).toFixed(0)}%`}
        className="block h-14 w-full"
        data-testid="eval-history-sparkline"
      >
        {chronological.length > 1 ? (
          <polyline
            points={points.join(" ")}
            className="fill-none stroke-accent"
            strokeWidth={1.5}
            strokeLinejoin="round"
            strokeLinecap="round"
            data-testid="eval-history-sparkline-line"
          />
        ) : null}
        {/* Latest run gets a dot so a single recorded run still renders. */}
        <circle
          cx={x(chronological.length - 1)}
          cy={y(latest.pass_rate)}
          r={2.5}
          className="fill-accent"
        />
      </svg>
    </div>
  );
}

function EvalRunTable(props: { runs: EvalRun[] }) {
  return (
    <div className="overflow-x-auto rounded-card bg-surface shadow-card">
      <table className="w-full text-sm" data-testid="eval-history-table">
        <thead className="border-b border-line text-xs text-ink-600 uppercase">
          <tr>
            <th className="px-3 py-2 text-left">Run at</th>
            <th className="px-3 py-2 text-left">Source</th>
            <th className="px-3 py-2 text-left">Runtime</th>
            <th className="px-3 py-2 text-right">Questions</th>
            <th className="px-3 py-2 text-right">Pass %</th>
            <th className="px-3 py-2 text-right">Halluc %</th>
            <th className="px-3 py-2 text-right">Leaks</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {props.runs.map((run) => {
            const leaks = run.cross_engagement_leak_count;
            return (
              <tr key={run.id} data-testid={`eval-history-row-${run.id}`}>
                <td className="text-ink-700 px-3 py-2 font-mono text-xs">
                  {new Date(run.run_at).toISOString()}
                </td>
                <td className="px-3 py-2 font-mono text-xs">{run.source}</td>
                <td className="px-3 py-2 font-mono text-xs">{run.runtime ?? "—"}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{run.question_count}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">
                  {(run.pass_rate * 100).toFixed(1)}
                </td>
                <td className="px-3 py-2 text-right font-mono text-xs">
                  {(run.hallucination_rate * 100).toFixed(1)}
                </td>
                <td
                  className="px-3 py-2 text-right font-mono text-xs"
                  data-testid={`eval-history-leaks-${run.id}`}
                  data-leaks={leaks > 0 ? "red" : "ok"}
                >
                  {/* Any cross-engagement leak is a security event — red, always. */}
                  <span
                    className={
                      leaks > 0
                        ? "inline-block rounded-md bg-red-tint px-1.5 py-0.5 font-semibold text-red-ink"
                        : ""
                    }
                  >
                    {leaks}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
