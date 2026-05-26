import type { Metadata } from "next";

import { ApiKeyList } from "@/components/settings/ApiKeyList.client";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "MCP API keys",
  description:
    "Mint and revoke bearer tokens for the DeployAI MCP server. Each token scopes one Claude desktop (or any MCP client) to one engagement, read-only.",
};

export default async function ApiKeysSettingsPage() {
  await requireCanonicalRead();
  return (
    <div className="max-w-3xl space-y-6">
      <header>
        <h1 className="text-xl font-semibold">MCP API keys</h1>
        <p className="text-ink-600 mt-1 text-sm">
          Mint bearer tokens for advisors to query an engagement&apos;s matrix and ledger from their
          own MCP client (Claude desktop, Continue, etc.). The raw key is shown ONCE on creation —
          copy it before dismissing the dialog. Revoking a key takes effect on the next request.
        </p>
      </header>
      <ApiKeyList />
    </div>
  );
}
