"use client";

import * as React from "react";
import { usePathname } from "next/navigation";
import {
  AgentOutageBanner,
  type DeploymentPhaseId,
  type FreshnessSurface,
} from "@deployai/shared-ui";

import { useStrategistSurface } from "@/lib/epic8/strategist-surface-context";

import { ChromeTopBar } from "./ChromeTopBar";
import { StrategistCommandPalette } from "./StrategistCommandPalette.client";
import { StrategistNav } from "./StrategistNav";

function freshnessForPath(pathname: string | null): FreshnessSurface {
  if (pathname === "/phase-tracking") {
    return "phase_tracking";
  }
  return "digest";
}

export type AppShellProps = {
  children: React.ReactNode;
  /** NFR5 — last successful memory sync (epoch ms). Set from the server layout. */
  lastSyncedAt: number | null;
  /** Overrides route-based default (e.g. tests). */
  freshnessSurface?: FreshnessSurface;
  currentPhaseId?: DeploymentPhaseId;
};

export function AppShell({
  children,
  lastSyncedAt,
  freshnessSurface: freshnessProp,
  currentPhaseId = "P5_pilot",
}: AppShellProps) {
  const pathname = usePathname();
  const { agentDegraded } = useStrategistSurface();
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
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="bg-background flex min-h-screen flex-col text-foreground">
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
          <div className="mx-auto w-full min-w-0 max-w-[1600px] flex-1 px-4 py-6 md:px-6">
            {children}
          </div>
        </div>
      </div>
      <StrategistCommandPalette open={commandOpen} onOpenChange={setCommandOpen} />
    </div>
  );
}
