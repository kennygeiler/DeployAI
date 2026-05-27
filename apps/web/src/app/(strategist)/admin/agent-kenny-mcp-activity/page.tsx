import type { Metadata } from "next";

import { McpActivityTable } from "@/components/admin/McpActivityTable.client";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "Agent Kenny — MCP activity",
  description:
    "Last 50 outbound MCP calls + configuration changes for this tenant, sourced from the audit ledger.",
};

/**
 * Wave 3I — admin panel for outbound-MCP audit visibility.
 *
 * Surfaces the redacted ledger rows that Wave 2D's ``mcp_client.py``
 * emits on every outbound call, plus the Wave 2E/2F config + killswitch
 * + oauth-rotation rows. Reads via the
 * ``/api/bff/tenant/mcp-activity`` BFF, which in turn calls the
 * tenant-scoped ``mcp_audit`` CP route added in this wave.
 *
 * The page is a thin shell — the client component handles fetch +
 * loading + render so a future "refresh" button or stream upgrade
 * doesn't require a server-side change.
 */
export default async function AgentKennyMcpActivityPage() {
  await requireCanonicalRead();
  return (
    <div className="max-w-6xl space-y-6 p-4">
      <header className="space-y-2">
        <h1 className="text-xl font-semibold">Agent Kenny — MCP activity</h1>
        <p className="text-ink-600 text-sm">
          Last 50 outbound MCP calls and configuration changes for this tenant. Detail blobs are
          already redacted by the control-plane emitter (
          <code className="font-mono text-xs">_SECRET_KEY_NEEDLES</code>) so OAuth tokens and bearer
          headers never reach this page.
        </p>
      </header>
      <McpActivityTable />
    </div>
  );
}
