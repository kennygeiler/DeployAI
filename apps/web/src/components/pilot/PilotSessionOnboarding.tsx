import Link from "next/link";

import type { StrategistIntegrationRecordsLoad } from "@/lib/internal/load-strategist-integration-records";

export type PilotDigestModeLabel = "mock" | "url" | "cp";

type Props = {
  tenantId: string | undefined;
  integrations: StrategistIntegrationRecordsLoad;
  digestMode: PilotDigestModeLabel;
};

/**
 * Epic 16.1 — landmarked first-session context: organization id, data mode, integration state, primary CTAs.
 */
export function PilotSessionOnboarding({ tenantId, integrations, digestMode }: Props) {
  const hasTenant = Boolean(tenantId?.trim());
  const activeIntegrations =
    integrations.status === "ok"
      ? integrations.items.filter((x) => x.state === "active" && !x.disabled_at)
      : [];
  const needsIntegrations = integrations.status === "ok" && activeIntegrations.length === 0;
  const primaryCta =
    needsIntegrations && hasTenant ? (
      <Link
        href="/settings/integrations"
        className="text-evidence-800 focus-visible:ring-ring font-medium underline underline-offset-2 focus-visible:rounded focus-visible:outline-none focus-visible:ring-2"
      >
        Connect integrations
      </Link>
    ) : (
      <Link
        href="/digest"
        className="text-evidence-800 focus-visible:ring-ring font-medium underline underline-offset-2 focus-visible:rounded focus-visible:outline-none focus-visible:ring-2"
      >
        Open morning digest
      </Link>
    );

  return (
    <section
      aria-labelledby="pilot-onboarding-heading"
      className="border-border bg-paper-50 border-b"
    >
      <div className="mx-auto w-full max-w-[1600px] px-4 py-3 md:px-6">
        <h2 id="pilot-onboarding-heading" className="text-ink-900 text-sm font-semibold">
          Your session
        </h2>
        <div className="text-ink-700 mt-2 space-y-1 text-sm">
          {!hasTenant ? (
            <p role="status">
              <span className="font-medium text-ink-900">Organization:</span> not scoped — sign in
              or configure tenant on your JWT or proxy headers (see pilot docs).
            </p>
          ) : (
            <p>
              <span className="font-medium text-ink-900">Organization id:</span>{" "}
              <span className="font-mono text-xs">{tenantId}</span>
            </p>
          )}
          <p>
            <span className="font-medium text-ink-900">Digest data:</span>{" "}
            {digestMode === "cp"
              ? "control plane pilot surface"
              : digestMode === "url"
                ? "remote JSON URL"
                : "demo fixtures (development / unset loaders)"}
          </p>
          {integrations.status === "unconfigured" ? (
            <p role="status">
              <span className="font-medium text-ink-900">Integrations:</span> control plane not
              configured — cannot list connection status from the web app.
            </p>
          ) : integrations.status === "error" ? (
            <p role="status">
              <span className="font-medium text-ink-900">Integrations:</span> could not load status
              from the control plane.
            </p>
          ) : needsIntegrations ? (
            <p role="status">
              <span className="font-medium text-ink-900">Integrations:</span> none active — connect
              Microsoft 365 (or other sources) to populate canonical memory.
            </p>
          ) : (
            <p>
              <span className="font-medium text-ink-900">Integrations:</span>{" "}
              {activeIntegrations.length} active — manage in{" "}
              <Link
                href="/settings/integrations"
                className="text-evidence-800 focus-visible:ring-ring underline underline-offset-2 focus-visible:rounded focus-visible:outline-none focus-visible:ring-2"
              >
                settings
              </Link>
              .
            </p>
          )}
          <p className="pt-1">
            <span className="font-medium text-ink-900">Next step:</span> {primaryCta}
          </p>
        </div>
      </div>
    </section>
  );
}
