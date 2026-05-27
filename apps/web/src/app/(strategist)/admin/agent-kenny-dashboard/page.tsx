import type { Metadata } from "next";

import { AgentKennyDashboardClient } from "@/components/admin/AgentKennyDashboardClient";
import {
  cpGetAgentKennyDashboard,
  WINDOW_DAYS_DEFAULT,
  type AgentKennyDashboard,
} from "@/lib/internal/agent-kenny-dashboard-cp";
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
    </div>
  );
}
