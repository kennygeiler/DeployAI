import type { Metadata } from "next";

import { AgentPromptsForm } from "@/components/settings/AgentPromptsForm.client";
import { LlmConfigForm } from "@/components/settings/LlmConfigForm.client";
import { MemberRolesForm } from "@/components/settings/MemberRolesForm.client";
import { NodeTypesForm } from "@/components/settings/NodeTypesForm.client";
import { WebhooksForm } from "@/components/settings/WebhooksForm.client";
import { t } from "@/lib/i18n";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: t("settings.heading"),
  description: "Tenant-scoped configuration for self-hosted DeployAI deployments.",
};

export default async function SettingsPage() {
  await requireCanonicalRead();
  return (
    <div className="max-w-5xl space-y-6">
      <header>
        <h1 className="text-xl font-semibold">{t("settings.heading")}</h1>
        <p className="text-ink-600 mt-1 text-sm">{t("settings.description")}</p>
        <p className="text-ink-600 mt-2 text-sm">
          <a className="underline" href="/settings/audit">
            {t("settings.auditLogLink")}
          </a>
          {" · "}
          <a className="underline" href="/settings/email-import">
            {t("settings.emailImportLink")}
          </a>
        </p>
      </header>
      <LlmConfigForm />
      <AgentPromptsForm />
      <WebhooksForm />
      <NodeTypesForm />
      <MemberRolesForm />
    </div>
  );
}
