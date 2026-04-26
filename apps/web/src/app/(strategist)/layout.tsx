import type { ReactNode } from "react";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { loadStrategistActivityForActor } from "@/lib/internal/load-strategist-activity";
import { getStrategistLastSyncedAtMs } from "@/lib/internal/strategist-last-synced";
import { StrategistShell } from "./StrategistShell.client";

export default async function StrategistLayout({ children }: { children: ReactNode }) {
  const lastSyncedAt = getStrategistLastSyncedAtMs();
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
