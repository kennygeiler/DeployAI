import type { Metadata } from "next";

import { AgentPromptsForm } from "@/components/settings/AgentPromptsForm.client";
import { LlmConfigForm } from "@/components/settings/LlmConfigForm.client";
import { WebhooksForm } from "@/components/settings/WebhooksForm.client";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "Settings",
  description: "Tenant-scoped configuration for self-hosted DeployAI deployments.",
};

export default async function SettingsPage() {
  await requireCanonicalRead();
  return (
    <div className="max-w-5xl space-y-6">
      <header>
        <h1 className="text-xl font-semibold">Settings</h1>
        <p className="text-ink-600 mt-1 text-sm">
          DeployAI runs self-hosted on your team&apos;s infrastructure. Configure the LLM provider
          your team uses for extraction + synthesis here. The API key is stored in the local
          database.
        </p>
      </header>
      <LlmConfigForm />
      <AgentPromptsForm />
      <WebhooksForm />
    </div>
  );
}
