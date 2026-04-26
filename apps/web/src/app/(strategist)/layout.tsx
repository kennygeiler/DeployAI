import type { ReactNode } from "react";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { loadStrategistActivityForActor } from "@/lib/internal/load-strategist-activity";
import { StrategistShell } from "./StrategistShell.client";

export default async function StrategistLayout({ children }: { children: ReactNode }) {
  // NFR5: chip shows “stale but plausible” last sync (~90s ago) at request time in dev.
  const lastSyncedAt = Date.now() - 90_000;
  const actor = await getActorFromHeaders();
  const initialActivity = await loadStrategistActivityForActor(actor);
  return (
    <StrategistShell lastSyncedAt={lastSyncedAt} initialActivity={initialActivity}>
      <main id="main" tabIndex={-1} className="outline-none">
        {children}
      </main>
    </StrategistShell>
  );
}
