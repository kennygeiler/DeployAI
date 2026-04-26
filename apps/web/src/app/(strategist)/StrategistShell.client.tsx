"use client";

import * as React from "react";

import { AppShell } from "@/components/chrome/AppShell";
import type { StrategistActivitySnapshot } from "@/lib/internal/load-strategist-activity";
import {
  StrategistSurfaceProvider,
  type StrategistSurfaceValue,
} from "@/lib/epic8/strategist-surface-context";

type Props = {
  children: React.ReactNode;
  lastSyncedAt: number;
  initialActivity: StrategistActivitySnapshot;
};

function toSurfaceValue(s: StrategistActivitySnapshot): StrategistSurfaceValue {
  return { agentDegraded: s.agentDegraded, ingestionInProgress: s.ingestionInProgress };
}

/**
 * Server passes initial `loadStrategistActivityForActor` snapshot; this client polls
 * `GET /api/internal/strategist-activity` (same logic) for live ingest + CP health.
 */
export function StrategistShell({ children, lastSyncedAt, initialActivity }: Props) {
  const [activity, setActivity] = React.useState<StrategistActivitySnapshot>(initialActivity);
  const requestId = React.useRef(0);

  const surface = React.useMemo(() => toSurfaceValue(activity), [activity]);

  const refresh = React.useCallback(() => {
    const id = (requestId.current += 1);
    void (async () => {
      const r = await fetch("/api/internal/strategist-activity", { cache: "no-store" });
      if (id !== requestId.current) {
        return;
      }
      if (!r.ok) {
        return;
      }
      const j = (await r.json()) as StrategistActivitySnapshot;
      setActivity(j);
    })();
  }, []);

  React.useEffect(() => {
    refresh();
  }, [refresh]);

  React.useEffect(() => {
    const t = setInterval(() => {
      if (document.visibilityState === "visible") {
        refresh();
      }
    }, 30_000);
    return () => clearInterval(t);
  }, [refresh]);

  return (
    <StrategistSurfaceProvider value={surface}>
      <AppShell lastSyncedAt={lastSyncedAt}>{children}</AppShell>
    </StrategistSurfaceProvider>
  );
}
