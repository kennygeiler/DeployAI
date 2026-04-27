"use client";

import * as React from "react";

import { AppShell } from "@/components/chrome/AppShell";
import { StrategistToaster } from "@/components/chrome/StrategistToaster";
import type { StrategistActivitySnapshot } from "@/lib/internal/load-strategist-activity";
import type { StrategistSessionBannerPayload } from "@/lib/internal/strategist-demo-session";
import { mergeStrategistSurfaceFromDemoQuery } from "@/lib/epic8/strategist-surface-flags";
import { getStrategistActivityPollIntervalMs } from "@/lib/epic9/strategist-activity-poll";
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
    inMeeting: s.inMeeting,
    meetingId: s.meetingId,
    meetingTitle: s.meetingTitle,
    oracleInMeetingAlertAt: s.oracleInMeetingAlertAt,
    meetingDetectionSource: s.meetingDetectionSource,
    calendarPollIntervalSeconds: s.calendarPollIntervalSeconds,
  };
}

/**
 * Subscribe to URL search changes without `useSearchParams` (avoids top-level Suspense that
 * broke ⌃K / Cmd+K E2E). Patch history only while this shell is mounted.
 */
function subscribeDemoSearch(onStoreChange: () => void): () => void {
  if (typeof window === "undefined") {
    return () => {};
  }
  const fire = () => {
    queueMicrotask(onStoreChange);
  };
  const origPush = history.pushState.bind(history);
  const origReplace = history.replaceState.bind(history);
  history.pushState = (...args: Parameters<History["pushState"]>) => {
    origPush(...args);
    fire();
  };
  history.replaceState = (...args: Parameters<History["replaceState"]>) => {
    origReplace(...args);
    fire();
  };
  window.addEventListener("popstate", fire);
  return () => {
    history.pushState = origPush;
    history.replaceState = origReplace;
    window.removeEventListener("popstate", fire);
  };
}

function getDemoSearchSnapshot(): string {
  return typeof window !== "undefined" ? window.location.search : "";
}

function getServerDemoSearchSnapshot(): string {
  return "";
}

/**
 * Server passes initial `loadStrategistActivityForActor` snapshot; this client polls
 * `GET /api/internal/strategist-activity` (same logic) for live ingest + CP health.
 *
 * Demo query flags (`?agentError=1`, `?ingest=1`, …) merge on top of the snapshot (Epic 8.7).
 * `useSyncExternalStore` reads `window.location.search` without `useSearchParams`/`Suspense`
 * and satisfies `react-hooks/set-state-in-effect` (no setState inside effects for the merge).
 *
 * Epic 9.1: visibility-gated poll of `/api/internal/strategist-activity` at
 * `getStrategistActivityPollIntervalMs()` (default 30 s, max 30 s; override via
 * `NEXT_PUBLIC_DEPLOYAI_STRATEGIST_ACTIVITY_POLL_MS` in dev builds).
 */
export function StrategistShell({ children, lastSyncedAt, initialActivity, sessionBanner }: Props) {
  const [activity, setActivity] = React.useState<StrategistActivitySnapshot>(initialActivity);
  const requestId = React.useRef(0);
  const pollIntervalMs = React.useMemo(() => getStrategistActivityPollIntervalMs(), []);

  const base = React.useMemo(() => toSurfaceValue(activity), [activity]);

  const demoSearch = React.useSyncExternalStore(
    subscribeDemoSearch,
    getDemoSearchSnapshot,
    getServerDemoSearchSnapshot,
  );

  const surface = React.useMemo(
    () => mergeStrategistSurfaceFromDemoQuery(base, demoSearch),
    [base, demoSearch],
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
        inMeeting: j.inMeeting ?? prev.inMeeting,
        meetingId: j.meetingId ?? prev.meetingId,
        meetingTitle: j.meetingTitle ?? prev.meetingTitle,
        oracleInMeetingAlertAt: j.oracleInMeetingAlertAt ?? prev.oracleInMeetingAlertAt,
        meetingDetectionSource: j.meetingDetectionSource ?? prev.meetingDetectionSource,
        calendarPollIntervalSeconds:
          j.calendarPollIntervalSeconds ?? prev.calendarPollIntervalSeconds,
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
    }, pollIntervalMs);
    return () => clearInterval(t);
  }, [refresh, pollIntervalMs]);

  return (
    <StrategistSurfaceProvider value={surface}>
      <StrategistToaster />
      <AppShell lastSyncedAt={lastSyncedAt} sessionBanner={sessionBanner}>
        {children}
      </AppShell>
    </StrategistSurfaceProvider>
  );
}
