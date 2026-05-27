import type { Metadata } from "next";

import { IntegrationsClient } from "@/components/settings/IntegrationsClient";
import {
  cpGetMcpKillSwitch,
  cpListMcpConfigs,
  type KillSwitchState,
  type TenantMcpConfigRead,
} from "@/lib/internal/mcp-configs-cp";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

/**
 * v2 Phase 5 Wave 3H — outbound-MCP integrations admin page.
 *
 * Server Component: pulls the kill-switch + config list from the CP via
 * the server-only client so the first paint already has data. The
 * Client Component below handles the create/edit/delete + the OAuth
 * bounce. All subsequent reads/writes go through the BFF routes under
 * ``/api/internal/v1/tenants/{tid}/...``.
 *
 * If CP env is misconfigured (no DEPLOYAI_CONTROL_PLANE_URL /
 * DEPLOYAI_INTERNAL_API_KEY), the loader catches the throw and renders
 * the page in degraded mode — empty list + an explainer banner — rather
 * than 500ing the whole strategist surface.
 */

export const metadata: Metadata = {
  title: "External integrations (MCP)",
  description:
    "Manage the curated catalog of external MCP servers (Slack, Linear, GDrive, Notion, GitHub) Agent Kenny may call. Includes the per-tenant kill switch for incident response.",
};

export const dynamic = "force-dynamic";

async function safeLoad(tenantId: string): Promise<{
  configs: TenantMcpConfigRead[];
  killSwitch: KillSwitchState;
  loadError: string | null;
}> {
  try {
    const [configs, killSwitch] = await Promise.all([
      cpListMcpConfigs(tenantId),
      cpGetMcpKillSwitch(tenantId),
    ]);
    return { configs, killSwitch, loadError: null };
  } catch (e) {
    return {
      configs: [],
      killSwitch: { disabled: false },
      loadError: e instanceof Error ? e.message : "Could not load integrations.",
    };
  }
}

export default async function IntegrationsSettingsPage() {
  const actor = await requireCanonicalRead();
  const tenantId = actor.tenantId?.trim() ?? "";
  const initial = tenantId
    ? await safeLoad(tenantId)
    : {
        configs: [] as TenantMcpConfigRead[],
        killSwitch: { disabled: false } as KillSwitchState,
        loadError: "No tenant context.",
      };
  return (
    <div className="max-w-5xl space-y-6">
      <header>
        <h1 className="text-xl font-semibold">External integrations (MCP)</h1>
        <p className="text-ink-600 mt-1 text-sm">
          Curated catalog of external MCP servers Agent Kenny may call. Enable the connectors your
          team uses, paste an OAuth token (or run the Slack flow), and restrict which tools Kenny
          may invoke per connector. The top-level kill switch immediately blocks all outbound MCP
          traffic for this tenant — use it for incident response.
        </p>
      </header>
      <IntegrationsClient
        tenantId={tenantId}
        initialConfigs={initial.configs}
        initialKillSwitch={initial.killSwitch}
        initialLoadError={initial.loadError}
      />
    </div>
  );
}
