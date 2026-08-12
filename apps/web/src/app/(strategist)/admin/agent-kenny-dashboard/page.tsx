import type { Metadata } from "next";

import { AdminRecentActivity } from "@/components/admin/AdminRecentActivity.client";
import { AgentKennyDashboardClient } from "@/components/admin/AgentKennyDashboardClient";
import { EvalHistorySection } from "@/components/admin/EvalHistorySection.client";
import {
  cpGetAgentKennyDashboard,
  WINDOW_DAYS_DEFAULT,
  type AgentKennyDashboard,
} from "@/lib/internal/agent-kenny-dashboard-cp";
import { cpListEvalRuns, type EvalRun } from "@/lib/internal/eval-runs-cp";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "Agent Kenny — dashboard",
  description:
    "Production telemetry for Agent Kenny v2: hallucination rate, tool-call distribution, latency percentiles, lint flags, top-cited events.",
};

export const dynamic = "force-dynamic";

/**
 * Phase 6 Wave C — strategist admin page for Agent Kenny telemetry.
 *
 * Server scaffold: enforces the canonical-read guard, pulls one window
 * of telemetry from the CP for the actor's tenant, and hands the initial
 * payload to the client component. The client handles the window selector,
 * the 60s auto-refresh, and the chart/table render — keeping the server
 * shell idempotent and the interactive bits where React state lives.
 *
 * If the CP env is not wired up (preview without backend) the page still
 * renders with ``null`` initialData; the client surfaces an empty-state
 * + retry button rather than throwing past the boundary.
 */
export default async function AgentKennyDashboardPage() {
  const actor = await requireCanonicalRead();
  const tenantId = actor.tenantId?.trim();

  let initialData: AgentKennyDashboard | null = null;
  let initialError: string | null = null;
  if (tenantId) {
    try {
      initialData = await cpGetAgentKennyDashboard(tenantId, {
        windowDays: WINDOW_DAYS_DEFAULT,
      });
    } catch (e) {
      initialError = e instanceof Error ? e.message : "Could not load dashboard.";
    }
  } else {
    initialError = "Actor missing tenant id.";
  }

  // Wave 4 (G8) — eval-run history is platform-level (no tenant scope):
  // fetch it independently so a CP hiccup here degrades to the section's
  // own error state without taking down the telemetry above it.
  let initialEvalRuns: EvalRun[] | null = null;
  let initialEvalRunsError: string | null = null;
  try {
    initialEvalRuns = await cpListEvalRuns({ limit: 50 });
  } catch (e) {
    initialEvalRunsError = e instanceof Error ? e.message : "Could not load eval history.";
  }

  return (
    <div className="max-w-6xl space-y-6 p-4">
      <header className="space-y-2">
        <h1 className="text-xl font-semibold">Agent Kenny — dashboard</h1>
        <p className="text-ink-600 text-sm">
          Live production telemetry: hallucination rate, latency percentiles, tool-call
          distribution, lint-flag breakdown, and the events Kenny cites most often. Numbers
          aggregate over <code className="font-mono text-xs">agent_audit_traces</code>,{" "}
          <code className="font-mono text-xs">ledger_events</code>, and{" "}
          <code className="font-mono text-xs">lint_flags</code> for this tenant.
        </p>
      </header>
      <AgentKennyDashboardClient
        tenantId={tenantId ?? null}
        initialData={initialData}
        initialError={initialError}
      />
      {/* Wave 4 (G8) — longitudinal eval quality: recorded golden-eval
          runs with a pass-rate sparkline. */}
      <EvalHistorySection initialRuns={initialEvalRuns} initialError={initialEvalRunsError} />
      {/* Wave 2.5 U3 — the per-engagement activity strip (agent tool
          invocations and other ledger events) lives here now, off the Brief. */}
      <AdminRecentActivity />
    </div>
  );
}
