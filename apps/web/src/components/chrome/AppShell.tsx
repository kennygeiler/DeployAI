"use client";

import * as React from "react";
import { usePathname } from "next/navigation";
import {
  AgentOutageBanner,
  SessionBanner,
  type DeploymentPhaseId,
  type FreshnessSurface,
} from "@deployai/shared-ui";
import type { StrategistSessionBannerPayload } from "@/lib/internal/strategist-demo-session";

import { useStrategistSurface } from "@/lib/epic8/strategist-surface-context";

import { ChromeTopBar } from "./ChromeTopBar";
import { StrategistCommandPalette } from "./StrategistCommandPalette.client";
import { StrategistNav } from "./StrategistNav";

function freshnessForPath(pathname: string | null): FreshnessSurface {
  if (pathname === "/phase-tracking") {
    return "phase_tracking";
  }
  /** Evening reuses digest NFR5 bands in `shared-ui` (same delivery class). */
  return "digest";
}

export type AppShellProps = {
  children: React.ReactNode;
  /** NFR5 — last successful memory sync (epoch ms). Set from the server layout. */
  lastSyncedAt: number | null;
  /** Overrides route-based default (e.g. tests). */
  freshnessSurface?: FreshnessSurface;
  currentPhaseId?: DeploymentPhaseId;
  /** Break-glass / external-auditor strip (Story 8.5) — from server env or future auth. */
  sessionBanner?: StrategistSessionBannerPayload | null;
  /** Epic 16.1 — onboarding / tenant context (server-rendered). */
  belowTopBar?: React.ReactNode;
};

export function AppShell({
  children,
  lastSyncedAt,
  freshnessSurface: freshnessProp,
  currentPhaseId = "P5_pilot",
  sessionBanner = null,
  belowTopBar = null,
}: AppShellProps) {
  const pathname = usePathname();
  const { agentDegraded, pilotMeetingPresenceAwaitingGraph } = useStrategistSurface();
  const [commandOpen, setCommandOpen] = React.useState(false);
  const freshnessSurface = freshnessProp ?? freshnessForPath(pathname);

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.repeat) {
        return;
      }
      if (e.defaultPrevented) {
        return;
      }
      if (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey) && !e.shiftKey && !e.altKey) {
        e.preventDefault();
        setCommandOpen((o) => !o);
      }
    };
    // Capture phase: runs before focused descendants handle the key, and before
    // React effects on child trees — pairs with E2E waiting on `command-palette-trigger`.
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, []);

  return (
    <div className="bg-background flex min-h-screen flex-col text-foreground">
      {sessionBanner ? (
        <div className="border-b border-amber-600/20 bg-amber-50/90">
          <div className="mx-auto w-full max-w-[1600px] px-2 pt-1 md:px-4">
            <SessionBanner
              sessionId={sessionBanner.sessionId}
              variant={sessionBanner.variant}
              expiresAt={sessionBanner.expiresAt}
            />
          </div>
        </div>
      ) : null}
      {pilotMeetingPresenceAwaitingGraph ? (
        <div className="border-b border-blue-600/15 bg-blue-50/85 dark:border-blue-800/40 dark:bg-blue-950/35">
          <div className="mx-auto w-full max-w-[1600px] px-4 py-2 text-sm leading-snug text-blue-950 md:px-6 dark:text-blue-50">
            Pilot: calendar-linked meeting presence is not active yet—the Microsoft Graph connector is
            still pending for this tenant. Stub or demo flows remain available where configured.
          </div>
        </div>
      ) : null}
      {agentDegraded ? (
        <div className="border-b border-border">
          <div className="mx-auto w-full max-w-[1600px] px-4 pt-2 md:px-6">
            <AgentOutageBanner
              agentName="Oracle"
              message="We will retry digest ranking. Canonical memory and citations remain available to read."
              variant="alert"
              retryAvailable
            />
          </div>
        </div>
      ) : null}
      <div className="flex min-h-0 min-w-0 flex-1">
        <StrategistNav />
        <div className="flex min-w-0 flex-1 flex-col">
          <ChromeTopBar
            lastSyncedAt={lastSyncedAt}
            freshnessSurface={freshnessSurface}
            currentPhaseId={currentPhaseId}
            onOpenCommandPalette={() => {
              setCommandOpen(true);
            }}
          />
          {belowTopBar}
          <div className="mx-auto w-full min-w-0 max-w-[1600px] flex-1 px-4 py-6 md:px-6">
            {children}
          </div>
        </div>
      </div>
      <StrategistCommandPalette open={commandOpen} onOpenChange={setCommandOpen} />
    </div>
  );
}
