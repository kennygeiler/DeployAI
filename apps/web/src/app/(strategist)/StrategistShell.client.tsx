"use client";

import * as React from "react";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { AppShell } from "@/components/chrome/AppShell";
import type { StrategistActivitySnapshot } from "@/lib/internal/load-strategist-activity";
import type { StrategistSessionBannerPayload } from "@/lib/internal/strategist-demo-session";
import { mergeStrategistSurfaceFromDemoQuery } from "@/lib/epic8/strategist-surface-flags";
import {
  StrategistSurfaceProvider,
  type StrategistSurfaceValue,
} from "@/lib/epic8/strategist-surface-context";

type Props = {
  children: React.ReactNode;
  lastSyncedAt: number;
  initialActivity: StrategistActivitySnapshot;
  sessionBanner: StrategistSessionBannerPayload | null;
};

function toSurfaceValue(s: StrategistActivitySnapshot): StrategistSurfaceValue {
  return {
    agentDegraded: s.agentDegraded,
    ingestionInProgress: s.ingestionInProgress,
    strategistLocalDate: s.strategistLocalDate,
  };
}

function StrategistShellFallback({
  children,
  lastSyncedAt,
  initialActivity,
  sessionBanner,
}: Props) {
  const surface = React.useMemo(
    () => mergeStrategistSurfaceFromDemoQuery(toSurfaceValue(initialActivity), ""),
    [initialActivity],
  );
  return (
    <StrategistSurfaceProvider value={surface}>
      <AppShell lastSyncedAt={lastSyncedAt} sessionBanner={sessionBanner}>
        {children}
      </AppShell>
    </StrategistSurfaceProvider>
  );
}

/**
 * Server passes initial `loadStrategistActivityForActor` snapshot; this client polls
 * `GET /api/internal/strategist-activity` (same logic) for live ingest + CP health.
 * Demo query flags (`?agentError=1`, `?ingest=1`, …) merge on top of the snapshot (Epic 8.7).
 */
function StrategistShellInner({
  children,
  lastSyncedAt,
  initialActivity,
  sessionBanner,
}: Props) {
  const searchParams = useSearchParams();
  const demoQueryString = searchParams.toString();
  const [activity, setActivity] = React.useState<StrategistActivitySnapshot>(initialActivity);
  const requestId = React.useRef(0);

  const surface = React.useMemo(
    () => mergeStrategistSurfaceFromDemoQuery(toSurfaceValue(activity), demoQueryString),
    [activity, demoQueryString],
  );

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
      setActivity((prev) => ({
        ...j,
        strategistLocalDate: j.strategistLocalDate ?? prev.strategistLocalDate,
        agentServiceHealth: j.agentServiceHealth ?? prev.agentServiceHealth,
      }));
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
      <AppShell lastSyncedAt={lastSyncedAt} sessionBanner={sessionBanner}>
        {children}
      </AppShell>
    </StrategistSurfaceProvider>
  );
}

export function StrategistShell(props: Props) {
  return (
    <Suspense fallback={<StrategistShellFallback {...props} />}>
      <StrategistShellInner {...props} />
    </Suspense>
  );
}
