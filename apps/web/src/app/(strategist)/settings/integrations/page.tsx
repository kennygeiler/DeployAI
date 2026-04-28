import type { Metadata } from "next";

import { DisableIntegrationForm } from "./DisableIntegrationForm.client";
import { getControlPlaneBaseUrl } from "@/lib/internal/control-plane";
import { loadStrategistIntegrationRecords } from "@/lib/internal/load-strategist-integration-records";
import { getPublicOriginFromHeaders } from "@/lib/internal/web-public-origin";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "Integrations",
  description: "Connect Microsoft 365 and other ingestion sources (Epic 16).",
};

export default async function IntegrationsSettingsPage() {
  const actor = await requireCanonicalRead();
  const integrations = await loadStrategistIntegrationRecords(actor);
  const cp = getControlPlaneBaseUrl();
  const origin = await getPublicOriginFromHeaders();
  const tid = actor.tenantId?.trim();
  const returnTo = `${origin}/settings/integrations`;
  const cpBase = cp?.replace(/\/$/, "");
  const calendarConnect =
    tid && cpBase
      ? `${cpBase}/integrations/m365-calendar/connect?tenant_id=${encodeURIComponent(tid)}&return_to=${encodeURIComponent(returnTo)}`
      : null;
  const mailConnect =
    tid && cpBase
      ? `${cpBase}/integrations/m365-mail/connect?tenant_id=${encodeURIComponent(tid)}&return_to=${encodeURIComponent(returnTo)}`
      : null;
  const teamsConnect =
    tid && cpBase
      ? `${cpBase}/integrations/m365-teams/connect?tenant_id=${encodeURIComponent(tid)}&return_to=${encodeURIComponent(returnTo)}`
      : null;

  return (
    <div className="flex max-w-3xl flex-col gap-8">
      <header>
        <h1 className="text-display text-ink-950 font-semibold tracking-tight">Integrations</h1>
        <p className="text-body text-ink-600 mt-2">
          Connect Microsoft 365 so ingestion can populate canonical memory for your organization.
          OAuth completes on the control plane; your platform may need to forward JWTs — see{" "}
          <span className="font-mono text-xs">docs/pilot/oauth-from-web.md</span>.
        </p>
      </header>

      <section aria-labelledby="connect-heading" className="rounded-lg border border-border p-4">
        <h2 id="connect-heading" className="text-ink-900 text-base font-semibold">
          Connect Microsoft 365
        </h2>
        <p className="text-ink-700 mt-2 text-sm">
          Links open the control plane OAuth start URL. You must be authorized there (Bearer access
          token or IdP session, per your deployment).
        </p>
        <ul className="mt-3 list-inside list-disc space-y-2 text-sm">
          <li>
            {calendarConnect ? (
              <a href={calendarConnect} className="text-evidence-800 font-medium underline">
                Calendar
              </a>
            ) : (
              <span className="text-ink-500">Calendar — configure tenant + control plane URL</span>
            )}
          </li>
          <li>
            {mailConnect ? (
              <a href={mailConnect} className="text-evidence-800 font-medium underline">
                Mail
              </a>
            ) : (
              <span className="text-ink-500">Mail — configure tenant + control plane URL</span>
            )}
          </li>
          <li>
            {teamsConnect ? (
              <a href={teamsConnect} className="text-evidence-800 font-medium underline">
                Teams transcripts
              </a>
            ) : (
              <span className="text-ink-500">Teams — configure tenant + control plane URL</span>
            )}
          </li>
        </ul>
      </section>

      <section aria-labelledby="status-heading" className="rounded-lg border border-border p-4">
        <h2 id="status-heading" className="text-ink-900 text-base font-semibold">
          Connection status
        </h2>
        {integrations.status === "unconfigured" ? (
          <p className="text-ink-700 mt-2 text-sm" role="status">
            Control plane URL or internal API key is not set on the web app — status unavailable.
          </p>
        ) : integrations.status === "error" ? (
          <p className="text-ink-700 mt-2 text-sm" role="status">
            Could not load integration records from the control plane.
          </p>
        ) : integrations.items.length === 0 ? (
          <p className="text-ink-700 mt-2 text-sm" role="status">
            No integrations registered yet for this tenant.
          </p>
        ) : (
          <ul className="mt-3 space-y-3">
            {integrations.items.map((row) => (
              <li
                key={row.id}
                className="border-border flex flex-col gap-2 rounded-md border p-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div>
                  <p className="text-ink-900 font-medium">{row.display_name}</p>
                  <p className="text-ink-600 font-mono text-xs">
                    {row.provider} · {row.state}
                    {row.disabled_at ? ` · disabled ${row.disabled_at}` : ""}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {calendarConnect && row.provider === "m365_calendar" && !row.disabled_at ? (
                    <a
                      href={calendarConnect}
                      className="text-evidence-800 text-sm font-medium underline"
                    >
                      Reconnect
                    </a>
                  ) : null}
                  {!row.disabled_at ? (
                    <DisableIntegrationForm integrationId={row.id} provider={row.provider} />
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
