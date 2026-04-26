import type { ReactNode } from "react";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { loadStrategistActivityForActor } from "@/lib/internal/load-strategist-activity";
import { getStrategistLastSyncedAtMs } from "@/lib/internal/strategist-last-synced";
import { getStrategistSessionBannerForEnv } from "@/lib/internal/strategist-demo-session";
import { StrategistShell } from "./StrategistShell.client";

export default async function StrategistLayout({ children }: { children: ReactNode }) {
  const lastSyncedAt = getStrategistLastSyncedAtMs();
  const actor = await getActorFromHeaders();
  const initialActivity = await loadStrategistActivityForActor(actor);
  const sessionBanner = getStrategistSessionBannerForEnv();
  return (
    <StrategistShell
      lastSyncedAt={lastSyncedAt}
      initialActivity={initialActivity}
      sessionBanner={sessionBanner}
    >
      <main id="main" tabIndex={-1} className="outline-none">
        {children}
      </main>
    </StrategistShell>
  );
}
