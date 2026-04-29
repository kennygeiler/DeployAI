import type { ReactNode } from "react";

import type { AuthActor } from "@deployai/authz";

import { PilotSessionOnboarding } from "@/components/pilot/PilotSessionOnboarding";
import { getActorFromHeaders } from "@/lib/internal/actor";
import { loadStrategistIntegrationRecords } from "@/lib/internal/load-strategist-integration-records";
import { loadStrategistActivityForActor } from "@/lib/internal/load-strategist-activity";
import { getStrategistLastSyncedAtMs } from "@/lib/internal/strategist-last-synced";
import { getStrategistSessionBannerForEnv } from "@/lib/internal/strategist-demo-session";
import { digestSurfacesUseControlPlane } from "@/lib/internal/strategist-pilot-tenant";
import { StrategistShell } from "./StrategistShell.client";

function digestModeLabel(actor: AuthActor | null): "mock" | "url" | "cp" {
  if (digestSurfacesUseControlPlane(actor)) {
    return "cp";
  }
  if (process.env.STRATEGIST_DIGEST_SOURCE_URL?.trim()) {
    return "url";
  }
  return "mock";
}

export default async function StrategistLayout({ children }: { children: ReactNode }) {
  const lastSyncedAt = getStrategistLastSyncedAtMs();
  const actor = await getActorFromHeaders();
  const initialActivity = await loadStrategistActivityForActor(actor);
  const sessionBanner = getStrategistSessionBannerForEnv();
  const integrations = await loadStrategistIntegrationRecords(actor);
  const pilotBelowTopBar = (
    <PilotSessionOnboarding
      tenantId={actor?.tenantId}
      integrations={integrations}
      digestMode={digestModeLabel(actor)}
    />
  );
  return (
    <StrategistShell
      lastSyncedAt={lastSyncedAt}
      initialActivity={initialActivity}
      sessionBanner={sessionBanner}
      pilotBelowTopBar={pilotBelowTopBar}
    >
      <main id="main" tabIndex={-1} className="outline-none">
        {children}
      </main>
    </StrategistShell>
  );
}
